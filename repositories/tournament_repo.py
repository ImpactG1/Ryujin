from typing import List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from models.tournament import Tournament, TournamentDispute, TournamentMatch, TournamentParticipant


class TournamentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_tournament(
        self,
        guild_id: int,
        title: str,
        description: Optional[str] = None,
        max_participants: int = 16,
    ) -> Tournament:
        tournament = Tournament(
            guild_id=guild_id,
            title=title,
            description=description,
            max_participants=max_participants,
            status="registration",
        )
        self.session.add(tournament)
        await self.session.flush()
        return tournament

    async def get_tournament(self, tournament_id: int) -> Optional[Tournament]:
        stmt = select(Tournament).where(Tournament.id == tournament_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_tournaments(self, guild_id: int) -> List[Tournament]:
        stmt = select(Tournament).where(Tournament.guild_id == guild_id).order_by(Tournament.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # --- Participants ---
    async def add_participant(self, tournament_id: int, user_id: int, seed: int) -> TournamentParticipant:
        part = TournamentParticipant(
            tournament_id=tournament_id,
            discord_user_id=user_id,
            seed=seed,
            status="registered",
        )
        self.session.add(part)
        await self.session.flush()
        return part

    async def get_participant(self, tournament_id: int, user_id: int) -> Optional[TournamentParticipant]:
        stmt = select(TournamentParticipant).where(
            TournamentParticipant.tournament_id == tournament_id,
            TournamentParticipant.discord_user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_participants(self, tournament_id: int) -> List[TournamentParticipant]:
        stmt = (
            select(TournamentParticipant)
            .where(TournamentParticipant.tournament_id == tournament_id)
            .order_by(TournamentParticipant.seed.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_participant_count(self, tournament_id: int) -> int:
        stmt = select(func.count(TournamentParticipant.id)).where(TournamentParticipant.tournament_id == tournament_id)
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0

    # --- Matches ---
    async def create_match(
        self,
        tournament_id: int,
        round_number: int,
        match_number: int,
        p1_id: Optional[int],
        p2_id: Optional[int],
        status: str = "pending",
        winner_id: Optional[int] = None,
    ) -> TournamentMatch:
        match = TournamentMatch(
            tournament_id=tournament_id,
            round_number=round_number,
            match_number=match_number,
            participant1_id=p1_id,
            participant2_id=p2_id,
            status=status,
            winner_id=winner_id,
        )
        self.session.add(match)
        await self.session.flush()
        return match

    async def get_match(self, match_id: int) -> Optional[TournamentMatch]:
        stmt = select(TournamentMatch).where(TournamentMatch.id == match_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_matches(self, tournament_id: int) -> List[TournamentMatch]:
        stmt = (
            select(TournamentMatch)
            .where(TournamentMatch.tournament_id == tournament_id)
            .order_by(TournamentMatch.round_number.asc(), TournamentMatch.match_number.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_match_by_round_and_number(
        self, tournament_id: int, round_number: int, match_number: int
    ) -> Optional[TournamentMatch]:
        stmt = select(TournamentMatch).where(
            TournamentMatch.tournament_id == tournament_id,
            TournamentMatch.round_number == round_number,
            TournamentMatch.match_number == match_number,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # --- Disputes ---
    async def create_dispute(self, match_id: int, raised_by_id: int, reason: str) -> TournamentDispute:
        dispute = TournamentDispute(
            match_id=match_id,
            raised_by_id=raised_by_id,
            reason=reason,
            status="open",
        )
        self.session.add(dispute)
        await self.session.flush()
        return dispute

    async def get_dispute(self, dispute_id: int) -> Optional[TournamentDispute]:
        stmt = select(TournamentDispute).where(TournamentDispute.id == dispute_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

