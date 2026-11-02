import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from core.permissions import has_sufficient_role
from models.tournament import Tournament, TournamentDispute, TournamentMatch, TournamentParticipant
from repositories.audit_repo import AuditRepository
from repositories.guild_repo import GuildRepository
from repositories.tournament_repo import TournamentRepository


class TournamentNotFoundError(Exception):
    pass


class TournamentFullError(Exception):
    pass


class DuplicateRegistrationError(Exception):
    pass


class TournamentStateError(Exception):
    pass


class TournamentPermissionError(Exception):
    pass


class MatchDisputeError(Exception):
    pass


class TournamentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.tournament_repo = TournamentRepository(session)
        self.guild_repo = GuildRepository(session)
        self.audit_repo = AuditRepository(session)

    async def create_tournament(
        self,
        guild_id: int,
        creator_id: int,
        creator_roles: List[str] | str,
        title: str,
        description: Optional[str] = None,
        max_participants: int = 16,
    ) -> Tournament:
        if not has_sufficient_role(creator_roles, "officer"):
            raise TournamentPermissionError("Only officers or higher can create tournaments.")

        await self.guild_repo.get_or_create_guild(guild_id)
        tournament = await self.tournament_repo.create_tournament(
            guild_id=guild_id,
            title=title,
            description=description,
            max_participants=max_participants,
        )

        await self.audit_repo.log_action(
            guild_id=guild_id,
            actor_id=creator_id,
            action="TOURNAMENT_CREATE",
            target_entity="tournament",
            target_id=str(tournament.id),
            details={"title": title, "max_participants": max_participants},
        )
        return tournament

    async def register_participant(self, tournament_id: int, user_id: int) -> TournamentParticipant:
        tournament = await self.tournament_repo.get_tournament(tournament_id)
        if not tournament:
            raise TournamentNotFoundError(f"Tournament {tournament_id} not found.")

        if tournament.status != "registration":
            raise TournamentStateError(f"Registration is not open (status: {tournament.status}).")

        # Check duplicate
        existing = await self.tournament_repo.get_participant(tournament_id, user_id)
        if existing:
            raise DuplicateRegistrationError("You are already registered for this tournament.")

        # Check cap
        count = await self.tournament_repo.get_participant_count(tournament_id)
        if count >= tournament.max_participants:
            raise TournamentFullError("Tournament participant cap reached.")

        seed = count + 1
        part = await self.tournament_repo.add_participant(tournament_id, user_id, seed=seed)

        await self.audit_repo.log_action(
            guild_id=tournament.guild_id,
            actor_id=user_id,
            action="TOURNAMENT_REGISTER",
            target_entity="tournament_participant",
            target_id=str(part.id),
            details={"seed": seed, "tournament_id": tournament.id},
        )
        return part

    async def generate_single_elimination_bracket(
        self,
        tournament_id: int,
        initiator_id: int,
        initiator_roles: List[str] | str,
    ) -> List[TournamentMatch]:
        """
        Generate a single-elimination bracket handling byes for non-power-of-2 participant counts.
        """
        if not has_sufficient_role(initiator_roles, "officer"):
            raise TournamentPermissionError("Only officers or higher can generate tournament brackets.")

        tournament = await self.tournament_repo.get_tournament(tournament_id)
        if not tournament:
            raise TournamentNotFoundError(f"Tournament {tournament_id} not found.")

        participants = await self.tournament_repo.list_participants(tournament_id)
        n = len(participants)
        if n < 2:
            raise TournamentStateError(f"Need at least 2 participants to generate a bracket (currently {n}).")

        # Calculate nearest power of 2 >= n
        p = 1
        while p < n:
            p *= 2

        total_rounds = int(math.log2(p))
        round1_match_count = p // 2

        # Create seeded slots (None represents a bye)
        slots = [p_obj.discord_user_id for p_obj in participants]
        while len(slots) < p:
            slots.append(None)

        # 1. Create all match placeholders for all rounds
        matches_by_round: Dict[int, List[TournamentMatch]] = {}
        for r in range(1, total_rounds + 1):
            matches_in_r = p // (2 ** r)
            matches_by_round[r] = []
            for m_num in range(1, matches_in_r + 1):
                m_obj = await self.tournament_repo.create_match(
                    tournament_id=tournament.id,
                    round_number=r,
                    match_number=m_num,
                    p1_id=None,
                    p2_id=None,
                    status="pending",
                )
                matches_by_round[r].append(m_obj)

        # 2. Populate Round 1 matches and resolve byes automatically
        for i in range(round1_match_count):
            p1 = slots[i * 2]
            p2 = slots[i * 2 + 1]
            match = matches_by_round[1][i]
            match.participant1_id = p1
            match.participant2_id = p2

            if p2 is None:
                # Bye match! p1 advances automatically
                match.status = "completed"
                match.winner_id = p1
                # Advance p1 to Round 2 if total_rounds > 1
                if total_rounds > 1:
                    r2_match_idx = i // 2
                    r2_match = matches_by_round[2][r2_match_idx]
                    if i % 2 == 0:
                        r2_match.participant1_id = p1
                    else:
                        r2_match.participant2_id = p1

        tournament.status = "in_progress"
        await self.session.flush()

        await self.audit_repo.log_action(
            guild_id=tournament.guild_id,
            actor_id=initiator_id,
            action="TOURNAMENT_BRACKET_GENERATED",
            target_entity="tournament",
            target_id=str(tournament.id),
            details={"participants": n, "bracket_size": p, "total_rounds": total_rounds},
        )

        return await self.tournament_repo.list_matches(tournament.id)

    async def report_match_score(
        self,
        match_id: int,
        reporter_id: int,
        reporter_roles: List[str] | str,
        score1: int,
        score2: int,
    ) -> TournamentMatch:
        match = await self.tournament_repo.get_match(match_id)
        if not match:
            raise TournamentNotFoundError(f"Match {match_id} not found.")

        if match.status not in ["pending", "disputed"]:
            raise TournamentStateError(f"Cannot report score for match with status '{match.status}'.")

        # Reporter must be participant in match OR officer+
        is_participant = (reporter_id in [match.participant1_id, match.participant2_id])
        is_officer = has_sufficient_role(reporter_roles, "officer")
        if not (is_participant or is_officer):
            raise TournamentPermissionError("Only participants of the match or officers can report scores.")

        if score1 == score2:
            raise ValueError("Match scores cannot be tied in single-elimination.")

        winner_id = match.participant1_id if score1 > score2 else match.participant2_id
        match.score1 = score1
        match.score2 = score2
        match.winner_id = winner_id
        match.status = "completed"

        # Advance winner to next round or complete tournament
        tournament = await self.tournament_repo.get_tournament(match.tournament_id)
        next_round_num = match.round_number + 1
        next_match_num = (match.match_number - 1) // 2 + 1

        next_match = await self.tournament_repo.get_match_by_round_and_number(
            tournament_id=match.tournament_id,
            round_number=next_round_num,
            match_number=next_match_num,
        )

        if next_match:
            if (match.match_number - 1) % 2 == 0:
                next_match.participant1_id = winner_id
            else:
                next_match.participant2_id = winner_id
        else:
            # Final match completed! Tournament winner determined
            tournament.status = "completed"
            part_winner = await self.tournament_repo.get_participant(tournament.id, winner_id)
            if part_winner:
                part_winner.status = "winner"

        await self.session.flush()

        await self.audit_repo.log_action(
            guild_id=tournament.guild_id,
            actor_id=reporter_id,
            action="MATCH_SCORE_REPORTED",
            target_entity="tournament_match",
            target_id=str(match.id),
            details={"score1": score1, "score2": score2, "winner_id": str(winner_id)},
        )

        return match

    async def raise_dispute(self, match_id: int, user_id: int, reason: str) -> TournamentDispute:
        match = await self.tournament_repo.get_match(match_id)
        if not match:
            raise TournamentNotFoundError(f"Match {match_id} not found.")

        if user_id not in [match.participant1_id, match.participant2_id]:
            raise TournamentPermissionError("Only participants in this match can raise a dispute.")

        if match.status == "disputed":
            raise MatchDisputeError("A dispute is already active for this match.")

        dispute = await self.tournament_repo.create_dispute(
            match_id=match_id,
            raised_by_id=user_id,
            reason=reason,
        )
        match.status = "disputed"
        await self.session.flush()

        tournament = await self.tournament_repo.get_tournament(match.tournament_id)
        await self.audit_repo.log_action(
            guild_id=tournament.guild_id,
            actor_id=user_id,
            action="MATCH_DISPUTE_RAISED",
            target_entity="tournament_dispute",
            target_id=str(dispute.id),
            details={"match_id": match.id, "reason": reason},
        )
        return dispute

    async def resolve_dispute(
        self,
        dispute_id: int,
        officer_id: int,
        officer_roles: List[str] | str,
        winner_id: int,
        officer_notes: Optional[str] = None,
    ) -> TournamentDispute:
        if not has_sufficient_role(officer_roles, "officer"):
            raise TournamentPermissionError("Only officers or higher can resolve disputes.")

        dispute = await self.tournament_repo.get_dispute(dispute_id)
        if not dispute:
            raise MatchDisputeError(f"Dispute {dispute_id} not found.")

        if dispute.status != "open":
            raise MatchDisputeError(f"Dispute is already {dispute.status}.")

        match = await self.tournament_repo.get_match(dispute.match_id)
        if winner_id not in [match.participant1_id, match.participant2_id]:
            raise ValueError(f"Winner {winner_id} is not one of the match participants.")

        # Resolve dispute
        dispute.status = "resolved"
        dispute.officer_notes = officer_notes
        dispute.resolved_by_id = officer_id
        dispute.resolved_at = datetime.now(timezone.utc)

        # Advance winner
        score1 = 1 if winner_id == match.participant1_id else 0
        score2 = 1 if winner_id == match.participant2_id else 0
        await self.report_match_score(
            match_id=match.id,
            reporter_id=officer_id,
            reporter_roles=officer_roles,
            score1=score1,
            score2=score2,
        )

        return dispute

    async def calculate_standings(self, tournament_id: int) -> List[Dict[str, Any]]:
        """Calculate final or current standings for the tournament."""
        matches = await self.tournament_repo.list_matches(tournament_id)
        if not matches:
            return []

        max_round = max(m.round_number for m in matches)
        final_match = next((m for m in matches if m.round_number == max_round), None)

        standings = []
        champion_id = final_match.winner_id if (final_match and final_match.status == "completed") else None
        runner_up_id = (
            (final_match.participant2_id if final_match.winner_id == final_match.participant1_id else final_match.participant1_id)
            if (final_match and final_match.status == "completed")
            else None
        )

        if champion_id:
            standings.append({"rank": 1, "discord_user_id": str(champion_id), "status": "Champion"})
        if runner_up_id:
            standings.append({"rank": 2, "discord_user_id": str(runner_up_id), "status": "Runner-Up"})

        # Semi-finals losers
        if max_round > 1:
            semi_matches = [m for m in matches if m.round_number == max_round - 1 and m.status == "completed"]
            for sm in semi_matches:
                loser_id = sm.participant2_id if sm.winner_id == sm.participant1_id else sm.participant1_id
                if loser_id and str(loser_id) not in [s["discord_user_id"] for s in standings]:
                    standings.append({"rank": 3, "discord_user_id": str(loser_id), "status": "Semi-Finalist"})

        return standings

    async def get_tournament(self, tournament_id: int) -> Optional[Tournament]:
        return await self.tournament_repo.get_tournament(tournament_id)

    async def list_matches(self, tournament_id: int) -> List[TournamentMatch]:
        return await self.tournament_repo.list_matches(tournament_id)

