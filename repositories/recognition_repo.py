from typing import List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.event import EventAttendance
from models.recognition import Achievement, MemberAward, MOTMRecord


class RecognitionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_achievement(
        self,
        guild_id: int,
        code: str,
        name: str,
        description: str,
        criteria_type: str,
        threshold: int,
        badge_icon: Optional[str] = None,
    ) -> Achievement:
        ach = Achievement(
            guild_id=guild_id,
            code=code.upper(),
            name=name,
            description=description,
            criteria_type=criteria_type,
            threshold=threshold,
            badge_icon=badge_icon,
        )
        self.session.add(ach)
        await self.session.flush()
        return ach

    async def get_achievement(self, achievement_id: int) -> Optional[Achievement]:
        stmt = select(Achievement).where(Achievement.id == achievement_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_achievement_by_code(self, guild_id: int, code: str) -> Optional[Achievement]:
        stmt = select(Achievement).where(
            Achievement.guild_id == guild_id,
            Achievement.code == code.upper(),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_achievements(self, guild_id: int) -> List[Achievement]:
        stmt = select(Achievement).where(Achievement.guild_id == guild_id).order_by(Achievement.id.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_award(self, guild_id: int, user_id: int, achievement_id: int) -> Optional[MemberAward]:
        stmt = select(MemberAward).where(
            MemberAward.guild_id == guild_id,
            MemberAward.discord_user_id == user_id,
            MemberAward.achievement_id == achievement_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_award(
        self,
        guild_id: int,
        user_id: int,
        achievement_id: int,
        awarded_by: Optional[int] = None,
    ) -> MemberAward:
        award = MemberAward(
            guild_id=guild_id,
            discord_user_id=user_id,
            achievement_id=achievement_id,
            awarded_by=awarded_by,
        )
        self.session.add(award)
        await self.session.flush()
        return award

    async def list_user_awards(self, guild_id: int, user_id: int) -> List[MemberAward]:
        stmt = select(MemberAward).where(
            MemberAward.guild_id == guild_id,
            MemberAward.discord_user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_events_attended(self, user_id: int) -> int:
        stmt = (
            select(func.count(EventAttendance.id))
            .where(
                EventAttendance.discord_user_id == user_id,
                EventAttendance.status == "present",
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0

    # --- MOTM ---
    async def get_motm(self, guild_id: int, year_month: str) -> Optional[MOTMRecord]:
        stmt = select(MOTMRecord).where(
            MOTMRecord.guild_id == guild_id,
            MOTMRecord.year_month == year_month,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def crown_motm(
        self,
        guild_id: int,
        year_month: str,
        user_id: int,
        reason: str,
        crowned_by: int,
    ) -> MOTMRecord:
        existing = await self.get_motm(guild_id, year_month)
        if existing:
            existing.discord_user_id = user_id
            existing.reason = reason
            existing.crowned_by = crowned_by
            await self.session.flush()
            return existing

        motm = MOTMRecord(
            guild_id=guild_id,
            year_month=year_month,
            discord_user_id=user_id,
            reason=reason,
            crowned_by=crowned_by,
        )
        self.session.add(motm)
        await self.session.flush()
        return motm

    async def get_motm_history(self, guild_id: int, limit: int = 24) -> List[MOTMRecord]:
        stmt = (
            select(MOTMRecord)
            .where(MOTMRecord.guild_id == guild_id)
            .order_by(MOTMRecord.year_month.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

