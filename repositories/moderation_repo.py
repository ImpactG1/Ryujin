from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from models.moderation import AuditLog, ModerationSanction


class ModerationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_sanction(
        self,
        guild_id: int,
        target_user_id: int,
        moderator_id: int,
        sanction_type: str,
        reason: str,
        duration_minutes: Optional[int] = None,
        expires_at: Optional[datetime] = None,
    ) -> ModerationSanction:
        sanction = ModerationSanction(
            guild_id=guild_id,
            target_user_id=target_user_id,
            moderator_id=moderator_id,
            sanction_type=sanction_type,
            reason=reason,
            duration_minutes=duration_minutes,
            expires_at=expires_at,
            is_active=True,
        )
        self.session.add(sanction)
        await self.session.flush()
        return sanction

    async def get_sanction(self, sanction_id: int) -> Optional[ModerationSanction]:
        stmt = select(ModerationSanction).where(ModerationSanction.id == sanction_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_sanctions(
        self,
        guild_id: int,
        target_user_id: Optional[int] = None,
        active_only: bool = False,
    ) -> List[ModerationSanction]:
        stmt = select(ModerationSanction).where(ModerationSanction.guild_id == guild_id)
        if target_user_id:
            stmt = stmt.where(ModerationSanction.target_user_id == target_user_id)
        if active_only:
            stmt = stmt.where(ModerationSanction.is_active == True)
        stmt = stmt.order_by(ModerationSanction.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def deactivate_sanction(self, sanction_id: int) -> Optional[ModerationSanction]:
        sanction = await self.get_sanction(sanction_id)
        if sanction:
            sanction.is_active = False
            await self.session.flush()
        return sanction

    async def count_user_recent_sanctions(self, guild_id: int, target_user_id: int, since: datetime) -> int:
        stmt = select(func.count(ModerationSanction.id)).where(
            ModerationSanction.guild_id == guild_id,
            ModerationSanction.target_user_id == target_user_id,
            ModerationSanction.created_at >= since,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0

    async def list_audit_logs(self, guild_id: int, limit: int = 50) -> List[AuditLog]:
        stmt = select(AuditLog).where(AuditLog.guild_id == guild_id).order_by(AuditLog.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

