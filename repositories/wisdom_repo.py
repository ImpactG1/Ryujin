from datetime import date
from typing import List, Optional
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.base import utc_now
from models.wisdom import DailyWisdom


class WisdomRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_wisdom_by_date(self, guild_id: int, target_date: date) -> Optional[DailyWisdom]:
        """Fetch the unlocked wisdom for a guild on a specific date."""
        stmt = select(DailyWisdom).where(
            DailyWisdom.guild_id == guild_id,
            DailyWisdom.date == target_date,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_wisdom(
        self,
        guild_id: int,
        target_date: date,
        quote: str,
        author: str,
        user_id: int,
    ) -> DailyWisdom:
        """Atomically persist today's unlocked wisdom quote."""
        record = DailyWisdom(
            guild_id=guild_id,
            date=target_date,
            quote=quote,
            author=author,
            unlocked_by_user_id=user_id,
            unlocked_at=utc_now(),
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_recent_wisdoms(self, guild_id: int, limit: int = 15) -> List[DailyWisdom]:
        """Fetch historical unlocked daily wisdom entries."""
        stmt = (
            select(DailyWisdom)
            .where(DailyWisdom.guild_id == guild_id)
            .order_by(desc(DailyWisdom.date))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

