from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.permissions import has_sufficient_role
from models.event import Event, EventAttendance
from models.squad import Squad, SquadJoinRequest, SquadMember
from repositories.audit_repo import AuditRepository
from repositories.guild_repo import GuildRepository
from repositories.squad_repo import SquadRepository


class SquadNotFoundError(Exception):
    pass


class SquadFullError(Exception):
    pass


class AlreadyMemberError(Exception):
    pass


class PendingRequestExistsError(Exception):
    pass


class InvalidRequestStateError(Exception):
    pass


class SquadPermissionError(Exception):
    pass


class SquadService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.squad_repo = SquadRepository(session)
        self.guild_repo = GuildRepository(session)
        self.audit_repo = AuditRepository(session)

    async def create_squad(
        self,
        guild_id: int,
        creator_id: int,
        creator_roles: List[str] | str,
        name: str,
        captain_id: int,
        capacity: int = 10,
    ) -> Squad:
        if not has_sufficient_role(creator_roles, "officer"):
            raise SquadPermissionError("Only officers or higher can create squads.")

        await self.guild_repo.get_or_create_guild(guild_id)
        squad = await self.squad_repo.create_squad(
            guild_id=guild_id,
            name=name,
            captain_id=captain_id,
            capacity=capacity,
        )

        await self.audit_repo.log_action(
            guild_id=guild_id,
            actor_id=creator_id,
            action="SQUAD_CREATE",
            target_entity="squad",
            target_id=str(squad.id),
            details={"name": name, "captain_id": str(captain_id), "capacity": capacity},
        )
        return squad

    async def request_to_join(self, squad_id: int, user_id: int) -> SquadJoinRequest:
        squad = await self.squad_repo.get_squad(squad_id)
        if not squad:
            raise SquadNotFoundError(f"Squad {squad_id} not found.")

        # 1. Check already a member
        existing_member = await self.squad_repo.get_member(squad_id, user_id)
        if existing_member:
            raise AlreadyMemberError("You are already a member of this squad.")

        # 2. Check pending request
        pending_req = await self.squad_repo.get_pending_request(squad_id, user_id)
        if pending_req:
            raise PendingRequestExistsError("You already have a pending join request for this squad.")

        # 3. Check capacity cap
        count = await self.squad_repo.get_member_count(squad_id)
        if count >= squad.capacity:
            raise SquadFullError("Squad is currently at full capacity.")

        req = await self.squad_repo.create_join_request(squad_id, user_id)
        await self.audit_repo.log_action(
            guild_id=squad.guild_id,
            actor_id=user_id,
            action="SQUAD_JOIN_REQUEST",
            target_entity="squad_join_request",
            target_id=str(req.id),
            details={"squad_id": squad.id},
        )
        return req

    async def review_join_request(
        self,
        request_id: int,
        reviewer_id: int,
        reviewer_roles: List[str] | str,
        decision: str,  # 'approved' or 'rejected'
        notes: Optional[str] = None,
    ) -> SquadJoinRequest:
        req = await self.squad_repo.get_join_request(request_id)
        if not req:
            raise InvalidRequestStateError(f"Join request {request_id} not found.")

        if req.status != "pending":
            raise InvalidRequestStateError(f"Join request is already {req.status}.")

        squad = await self.squad_repo.get_squad(req.squad_id)
        if not squad:
            raise SquadNotFoundError(f"Squad {req.squad_id} not found.")

        # Reviewer must be the squad's captain OR an officer+
        is_captain = (reviewer_id == squad.captain_id)
        is_officer = has_sufficient_role(reviewer_roles, "officer")
        if not (is_captain or is_officer):
            raise SquadPermissionError("Only the squad captain or an officer can review join requests.")

        now = datetime.now(timezone.utc)
        clean_decision = decision.strip().lower()

        if clean_decision == "approved":
            # Check capacity again before approving
            count = await self.squad_repo.get_member_count(squad.id)
            if count >= squad.capacity:
                raise SquadFullError("Cannot approve: squad has reached full capacity.")

            # Add to squad
            await self.squad_repo.add_member(squad.id, req.discord_user_id, role="member")
            req.status = "approved"
        elif clean_decision == "rejected":
            req.status = "rejected"
        else:
            raise ValueError(f"Invalid decision '{decision}'. Must be 'approved' or 'rejected'.")

        req.reviewer_id = reviewer_id
        req.reviewed_at = now
        req.notes = notes
        await self.session.flush()

        await self.audit_repo.log_action(
            guild_id=squad.guild_id,
            actor_id=reviewer_id,
            action=f"SQUAD_REQUEST_{clean_decision.upper()}",
            target_entity="squad_join_request",
            target_id=str(req.id),
            details={"target_user_id": str(req.discord_user_id), "squad_id": squad.id, "notes": notes},
        )
        return req

    async def get_squad_attendance_stats(self, squad_id: int) -> Dict[str, Any]:
        """Calculate aggregated attendance statistics for all members of the squad."""
        squad = await self.squad_repo.get_squad(squad_id)
        if not squad:
            raise SquadNotFoundError(f"Squad {squad_id} not found.")

        members = await self.squad_repo.list_members(squad_id)
        member_ids = [m.discord_user_id for m in members]

        # Count events targeted for this squad
        stmt_events = select(func.count(Event.id)).where(
            Event.guild_id == squad.guild_id,
            Event.status != "cancelled",
            (Event.target_squad_id == squad_id) | (Event.target_squad_id == None),
        )
        res_events = await self.session.execute(stmt_events)
        total_events = res_events.scalar_one() or 0

        # Query attendances by squad members
        member_stats = []
        total_squad_attendances = 0

        for m_id in member_ids:
            stmt_att = select(func.count(EventAttendance.id)).where(
                EventAttendance.discord_user_id == m_id,
                EventAttendance.status == "present",
            )
            res_att = await self.session.execute(stmt_att)
            att_count = res_att.scalar_one() or 0
            total_squad_attendances += att_count
            member_stats.append({
                "discord_user_id": str(m_id),
                "events_attended": att_count,
            })

        max_possible = len(member_ids) * total_events if total_events > 0 else 0
        overall_rate = round((total_squad_attendances / max_possible) * 100.0, 1) if max_possible > 0 else 0.0

        return {
            "squad_id": squad.id,
            "squad_name": squad.name,
            "member_count": len(members),
            "capacity": squad.capacity,
            "total_events": total_events,
            "total_attendances": total_squad_attendances,
            "attendance_rate_percent": overall_rate,
            "members": member_stats,
        }

    async def get_squad(self, squad_id: int) -> Optional[Squad]:
        return await self.squad_repo.get_squad(squad_id)

    async def list_squads(self, guild_id: int) -> List[Squad]:
        return await self.squad_repo.list_squads(guild_id)

    async def list_members(self, squad_id: int) -> List[SquadMember]:
        return await self.squad_repo.list_members(squad_id)

    async def list_join_requests(self, squad_id: int, status: Optional[str] = None) -> List[SquadJoinRequest]:
        return await self.squad_repo.list_join_requests(squad_id, status=status)

