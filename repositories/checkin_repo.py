from datetime import date
from typing import List, Optional
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from models.checkin import CheckIn, MemberStreak


class CheckInRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_checkin(self, guild_id: int, user_id: int, checkin_date: date) -> Optional[CheckIn]:
        stmt = select(CheckIn).where(
            CheckIn.guild_id == guild_id,
            CheckIn.discord_user_id == user_id,
            CheckIn.checkin_date == checkin_date,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_checkin(self, guild_id: int, user_id: int, checkin_date: date, streak_count: int) -> CheckIn:
        record = CheckIn(
            guild_id=guild_id,
            discord_user_id=user_id,
            checkin_date=checkin_date,
            streak_count=streak_count,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_or_create_streak(self, guild_id: int, user_id: int) -> MemberStreak:
        stmt = select(MemberStreak).where(
            MemberStreak.guild_id == guild_id,
            MemberStreak.discord_user_id == user_id,
        )
        result = await self.session.execute(stmt)
        streak = result.scalar_one_or_none()
        if not streak:
            streak = MemberStreak(
                guild_id=guild_id,
                discord_user_id=user_id,
                current_streak=0,
                longest_streak=0,
                last_checkin_date=None,
            )
            self.session.add(streak)
            await self.session.flush()
        return streak

    async def get_leaderboard(self, guild_id: int, limit: int = 10) -> List[MemberStreak]:
        stmt = (
            select(MemberStreak)
            .where(MemberStreak.guild_id == guild_id)
            .order_by(desc(MemberStreak.current_streak), desc(MemberStreak.longest_streak))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

