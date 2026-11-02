from datetime import date
from typing import List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from models.recruitment import LeaveRequest, RecruitmentApplication


class RecruitmentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # --- Applications ---
    async def create_application(
        self,
        guild_id: int,
        discord_tag: str,
        email: str,
        full_name: str,
        experience: str,
        answers_json: Optional[str] = None,
        discord_user_id: Optional[int] = None,
    ) -> RecruitmentApplication:
        app = RecruitmentApplication(
            guild_id=guild_id,
            discord_tag=discord_tag,
            email=email,
            full_name=full_name,
            experience=experience,
            answers_json=answers_json,
            discord_user_id=discord_user_id,
            status="pending",
        )
        self.session.add(app)
        await self.session.flush()
        return app

    async def get_application(self, application_id: int) -> Optional[RecruitmentApplication]:
        stmt = select(RecruitmentApplication).where(RecruitmentApplication.id == application_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_applications(self, guild_id: int, status: Optional[str] = None) -> List[RecruitmentApplication]:
        stmt = select(RecruitmentApplication).where(RecruitmentApplication.guild_id == guild_id)
        if status:
            stmt = stmt.where(RecruitmentApplication.status == status)
        stmt = stmt.order_by(RecruitmentApplication.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # --- Leave Requests ---
    async def create_leave_request(
        self,
        guild_id: int,
        user_id: int,
        start_date: date,
        end_date: date,
        reason: str,
    ) -> LeaveRequest:
        leave = LeaveRequest(
            guild_id=guild_id,
            discord_user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            status="pending",
        )
        self.session.add(leave)
        await self.session.flush()
        return leave

    async def get_leave_request(self, leave_id: int) -> Optional[LeaveRequest]:
        stmt = select(LeaveRequest).where(LeaveRequest.id == leave_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_overlapping_leaves(
        self,
        guild_id: int,
        user_id: int,
        start_date: date,
        end_date: date,
        exclude_leave_id: Optional[int] = None,
    ) -> List[LeaveRequest]:
        """Find approved or pending leaves that overlap with [start_date, end_date]."""
        stmt = select(LeaveRequest).where(
            LeaveRequest.guild_id == guild_id,
            LeaveRequest.discord_user_id == user_id,
            LeaveRequest.status.in_(["pending", "approved"]),
            LeaveRequest.start_date <= end_date,
            LeaveRequest.end_date >= start_date,
        )
        if exclude_leave_id:
            stmt = stmt.where(LeaveRequest.id != exclude_leave_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_leave_requests(self, guild_id: int, status: Optional[str] = None) -> List[LeaveRequest]:
        stmt = select(LeaveRequest).where(LeaveRequest.guild_id == guild_id)
        if status:
            stmt = stmt.where(LeaveRequest.status == status)
        stmt = stmt.order_by(LeaveRequest.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

