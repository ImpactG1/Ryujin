from typing import List, Optional
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from models.base import utc_now
from models.level import MemberLevel, RankHistory


class LevelRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_member_level(self, guild_id: int, user_id: int) -> MemberLevel:
        stmt = select(MemberLevel).where(
            MemberLevel.guild_id == guild_id,
            MemberLevel.discord_user_id == user_id,
        )
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            record = MemberLevel(
                guild_id=guild_id,
                discord_user_id=user_id,
                xp=0,
                level=0,
                rank_tier="D",
                previous_rank_tier=None,
                rank_updated_at=None,
                messages_count=0,
                last_message_at=None,
            )
            self.session.add(record)
            await self.session.flush()
        return record

    async def get_member_level(self, guild_id: int, user_id: int) -> Optional[MemberLevel]:
        stmt = select(MemberLevel).where(
            MemberLevel.guild_id == guild_id,
            MemberLevel.discord_user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_leaderboard(self, guild_id: int, limit: int = 10) -> List[MemberLevel]:
        stmt = (
            select(MemberLevel)
            .where(MemberLevel.guild_id == guild_id)
            .order_by(desc(MemberLevel.xp), desc(MemberLevel.messages_count))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_member_rank(self, guild_id: int, user_id: int) -> int:
        """Calculate the numerical rank of a member based on total XP (1-indexed)."""
        member = await self.get_member_level(guild_id, user_id)
        user_xp = member.xp if member else 0

        stmt = select(func.count(MemberLevel.id)).where(
            MemberLevel.guild_id == guild_id,
            MemberLevel.xp > user_xp,
        )
        result = await self.session.execute(stmt)
        higher_count = result.scalar_one() or 0
        return higher_count + 1

    async def record_rank_change(
        self,
        guild_id: int,
        user_id: int,
        from_tier: str,
        to_tier: str,
        change_type: str,
        actor_id: int = 0,
        reason: Optional[str] = None,
    ) -> RankHistory:
        """Record a promotion, demotion, or sync event in rank history."""
        history = RankHistory(
            guild_id=guild_id,
            discord_user_id=user_id,
            from_tier=from_tier,
            to_tier=to_tier,
            change_type=change_type,
            actor_id=actor_id,
            reason=reason,
            created_at=utc_now(),
        )
        self.session.add(history)
        await self.session.flush()
        return history

    async def get_rank_history(
        self,
        guild_id: int,
        user_id: int,
        limit: int = 20,
    ) -> List[RankHistory]:
        """Fetch rank promotion/demotion history for a member."""
        stmt = (
            select(RankHistory)
            .where(
                RankHistory.guild_id == guild_id,
                RankHistory.discord_user_id == user_id,
            )
            .order_by(desc(RankHistory.created_at), desc(RankHistory.id))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_rank_change(
        self,
        guild_id: int,
        user_id: int,
    ) -> Optional[RankHistory]:
        """Fetch the most recent rank promotion or demotion record."""
        stmt = (
            select(RankHistory)
            .where(
                RankHistory.guild_id == guild_id,
                RankHistory.discord_user_id == user_id,
            )
            .order_by(desc(RankHistory.created_at), desc(RankHistory.id))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
