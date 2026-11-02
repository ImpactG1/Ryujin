from datetime import date, datetime, time, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.permissions import has_sufficient_role
from models.event import Event
from models.recruitment import LeaveRequest
from repositories.audit_repo import AuditRepository
from repositories.guild_repo import GuildRepository
from repositories.recruitment_repo import RecruitmentRepository


class LeaveConflictError(Exception):
    pass


class LeaveNotFoundError(Exception):
    pass


class LeavePermissionError(Exception):
    pass


class LeaveService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.recruitment_repo = RecruitmentRepository(session)
        self.guild_repo = GuildRepository(session)
        self.audit_repo = AuditRepository(session)

    async def submit_leave_request(
        self,
        guild_id: int,
        user_id: int,
        start_date: date,
        end_date: date,
        reason: str,
    ) -> Dict[str, Any]:
        """
        Submit a member leave request with comprehensive conflict checks:
        1. Validates start_date <= end_date.
        2. Checks for overlapping pending/approved leaves for this member.
        3. Identifies and flags conflicting scheduled guild events.
        """
        if start_date > end_date:
            raise ValueError("Leave start date cannot be after end date.")

        await self.guild_repo.get_or_create_guild(guild_id)

        # 1. Overlapping leave check
        overlapping = await self.recruitment_repo.find_overlapping_leaves(
            guild_id=guild_id,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )
        if overlapping:
            raise LeaveConflictError(
                f"You already have an existing leave request ({overlapping[0].start_date} to {overlapping[0].end_date}) overlapping these dates."
            )

        # 2. Conflicting scheduled events check
        start_dt = datetime.combine(start_date, time.min).replace(tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, time.max).replace(tzinfo=timezone.utc)

        stmt_events = select(Event).where(
            Event.guild_id == guild_id,
            Event.status == "scheduled",
            Event.start_time <= end_dt,
            Event.end_time >= start_dt,
        )
        res_events = await self.session.execute(stmt_events)
        conflicting_events = [
            {"id": ev.id, "title": ev.title, "start_time": ev.start_time.isoformat()}
            for ev in res_events.scalars().all()
        ]

        leave = await self.recruitment_repo.create_leave_request(
            guild_id=guild_id,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
        )

        await self.audit_repo.log_action(
            guild_id=guild_id,
            actor_id=user_id,
            action="LEAVE_REQUEST_SUBMITTED",
            target_entity="leave_request",
            target_id=str(leave.id),
            details={
                "start_date": str(start_date),
                "end_date": str(end_date),
                "conflicting_events_count": len(conflicting_events),
            },
        )

        return {
            "id": leave.id,
            "guild_id": leave.guild_id,
            "discord_user_id": str(leave.discord_user_id),
            "start_date": str(leave.start_date),
            "end_date": str(leave.end_date),
            "reason": leave.reason,
            "status": leave.status,
            "conflicting_events": conflicting_events,
        }

    async def review_leave_request(
        self,
        leave_id: int,
        reviewer_id: int,
        reviewer_roles: List[str] | str,
        decision: str,  # 'approved' or 'rejected'
    ) -> Dict[str, Any]:
        if not has_sufficient_role(reviewer_roles, "officer"):
            raise LeavePermissionError("Only officers or higher can review leave requests.")

        leave = await self.recruitment_repo.get_leave_request(leave_id)
        if not leave:
            raise LeaveNotFoundError(f"Leave request {leave_id} not found.")

        clean_decision = decision.strip().lower()
        if clean_decision not in ["approved", "rejected"]:
            raise ValueError("Decision must be 'approved' or 'rejected'.")

        leave.status = clean_decision
        leave.reviewer_id = reviewer_id
        leave.reviewed_at = datetime.now(timezone.utc)
        await self.session.flush()

        await self.audit_repo.log_action(
            guild_id=leave.guild_id,
            actor_id=reviewer_id,
            action=f"LEAVE_{clean_decision.upper()}",
            target_entity="leave_request",
            target_id=str(leave.id),
            details={"target_user_id": str(leave.discord_user_id)},
        )

        return {
            "id": leave.id,
            "status": leave.status,
            "reviewer_id": str(reviewer_id),
            "reviewed_at": leave.reviewed_at.isoformat(),
        }

    async def list_leave_requests(self, guild_id: int, status: Optional[str] = None) -> List[LeaveRequest]:
        return await self.recruitment_repo.list_leave_requests(guild_id, status=status)

