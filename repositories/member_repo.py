from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.member import Member, RoleWeight


class MemberRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_member(self, guild_id: int, user_id: int) -> Optional[Member]:
        stmt = select(Member).where(
            Member.guild_id == guild_id,
            Member.discord_user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def provision_member(
        self,
        guild_id: int,
        user_id: int,
        username: str,
        display_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> Member:
        member = await self.get_member(guild_id, user_id)
        if member:
            member.is_active = True
            member.username = username
            if display_name:
                member.display_name = display_name
            if avatar_url:
                member.avatar_url = avatar_url
            await self.session.flush()
            return member

        new_member = Member(
            guild_id=guild_id,
            discord_user_id=user_id,
            username=username,
            display_name=display_name or username,
            avatar_url=avatar_url,
            is_active=True,
        )
        self.session.add(new_member)
        await self.session.flush()
        return new_member

    async def list_members(self, guild_id: int, active_only: bool = True) -> List[Member]:
        stmt = select(Member).where(Member.guild_id == guild_id)
        if active_only:
            stmt = stmt.where(Member.is_active == True)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

