from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.guild import Guild, GuildConfig
from core.config import settings


class GuildRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_guild(self, guild_id: int, name: str = "Ryujin Community") -> Guild:
        stmt = select(Guild).where(Guild.guild_id == guild_id)
        result = await self.session.execute(stmt)
        guild = result.scalar_one_or_none()
        if not guild:
            guild = Guild(
                guild_id=guild_id,
                name=name,
                timezone=settings.DEFAULT_TIMEZONE,
                is_active=True,
            )
            self.session.add(guild)
            config = GuildConfig(guild_id=guild_id)
            self.session.add(config)
            await self.session.flush()
        return guild

    async def get_guild_timezone(self, guild_id: int) -> str:
        stmt = select(Guild.timezone).where(Guild.guild_id == guild_id)
        result = await self.session.execute(stmt)
        tz = result.scalar_one_or_none()
        return tz or settings.DEFAULT_TIMEZONE

