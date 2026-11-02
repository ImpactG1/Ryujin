from typing import List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from models.squad import Squad, SquadJoinRequest, SquadMember


class SquadRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_squad(
        self,
        guild_id: int,
        name: str,
        captain_id: int,
        capacity: int = 10,
    ) -> Squad:
        squad = Squad(
            guild_id=guild_id,
            name=name,
            captain_id=captain_id,
            capacity=capacity,
        )
        self.session.add(squad)
        await self.session.flush()

        # Add captain as first member
        captain_member = SquadMember(
            squad_id=squad.id,
            discord_user_id=captain_id,
            role="captain",
        )
        self.session.add(captain_member)
        await self.session.flush()
        return squad

    async def get_squad(self, squad_id: int) -> Optional[Squad]:
        stmt = select(Squad).where(Squad.id == squad_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_squads(self, guild_id: int) -> List[Squad]:
        stmt = select(Squad).where(Squad.guild_id == guild_id).order_by(Squad.name.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_member_count(self, squad_id: int) -> int:
        stmt = select(func.count(SquadMember.id)).where(SquadMember.squad_id == squad_id)
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0

    async def get_member(self, squad_id: int, user_id: int) -> Optional[SquadMember]:
        stmt = select(SquadMember).where(
            SquadMember.squad_id == squad_id,
            SquadMember.discord_user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_member(self, squad_id: int, user_id: int, role: str = "member") -> SquadMember:
        member = SquadMember(
            squad_id=squad_id,
            discord_user_id=user_id,
            role=role,
        )
        self.session.add(member)
        await self.session.flush()
        return member

    async def list_members(self, squad_id: int) -> List[SquadMember]:
        stmt = select(SquadMember).where(SquadMember.squad_id == squad_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # --- Join Requests ---
    async def create_join_request(self, squad_id: int, user_id: int) -> SquadJoinRequest:
        req = SquadJoinRequest(
            squad_id=squad_id,
            discord_user_id=user_id,
            status="pending",
        )
        self.session.add(req)
        await self.session.flush()
        return req

    async def get_join_request(self, request_id: int) -> Optional[SquadJoinRequest]:
        stmt = select(SquadJoinRequest).where(SquadJoinRequest.id == request_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_pending_request(self, squad_id: int, user_id: int) -> Optional[SquadJoinRequest]:
        stmt = select(SquadJoinRequest).where(
            SquadJoinRequest.squad_id == squad_id,
            SquadJoinRequest.discord_user_id == user_id,
            SquadJoinRequest.status == "pending",
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_join_requests(self, squad_id: int, status: Optional[str] = None) -> List[SquadJoinRequest]:
        stmt = select(SquadJoinRequest).where(SquadJoinRequest.squad_id == squad_id)
        if status:
            stmt = stmt.where(SquadJoinRequest.status == status)
        stmt = stmt.order_by(SquadJoinRequest.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

