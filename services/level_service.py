from datetime import datetime, timedelta, timezone
import random
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from core.permissions import has_sufficient_role
from models.level import MemberLevel
from repositories.audit_repo import AuditRepository
from repositories.guild_repo import GuildRepository
from repositories.level_repo import LevelRepository


def xp_for_next_level(level: int) -> int:
    """Calculates XP required to advance from `level` to `level + 1`."""
    return 5 * (level ** 2) + 50 * level + 100


def calculate_level_from_xp(total_xp: int) -> tuple[int, int, int]:
    """
    Given total cumulative XP, returns:
    (current_level, xp_into_current_level, xp_needed_for_next_level)
    """
    level = 0
    remaining = total_xp
    while True:
        req = xp_for_next_level(level)
        if remaining < req:
            return level, remaining, req
        remaining -= req
        level += 1


class LevelPermissionError(Exception):
    pass


class LevelService:
    COOLDOWN_SECONDS = 60  # Cooldown between XP gains to prevent spam

    def __init__(self, session: AsyncSession):
        self.session = session
        self.level_repo = LevelRepository(session)
        self.guild_repo = GuildRepository(session)
        self.audit_repo = AuditRepository(session)

    async def process_message_activity(
        self,
        guild_id: int,
        user_id: int,
        current_time: Optional[datetime] = None,
        base_xp: int = 20,
    ) -> Dict[str, Any]:
        """
        Record a member's chat message activity:
        - Increments total messages count.
        - Grants XP if cooldown (60s) has passed.
        - Calculates current level and triggers level-up flag if milestone is achieved.
        """
        await self.guild_repo.get_or_create_guild(guild_id)
        record = await self.level_repo.get_or_create_member_level(guild_id, user_id)

        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        # 1. Increment total messages
        record.messages_count += 1

        # 2. Check cooldown for XP grant
        awarded_xp = 0
        can_grant_xp = False
        if record.last_message_at is None:
            can_grant_xp = True
        else:
            last_msg = record.last_message_at
            if last_msg.tzinfo is None:
                last_msg = last_msg.replace(tzinfo=timezone.utc)
            if (now - last_msg).total_seconds() >= self.COOLDOWN_SECONDS:
                can_grant_xp = True

        if can_grant_xp:
            awarded_xp = base_xp
            record.xp += awarded_xp
            record.last_message_at = now

        # 3. Recalculate level
        new_level, current_lvl_xp, needed_xp = calculate_level_from_xp(record.xp)
        old_level = record.level
        leveled_up = new_level > old_level
        record.level = new_level

        await self.session.flush()

        # 4. Audit log on level up
        if leveled_up:
            await self.audit_repo.log_action(
                guild_id=guild_id,
                actor_id=user_id,
                action="MEMBER_LEVEL_UP",
                target_entity="member_level",
                target_id=str(record.id),
                details={
                    "old_level": old_level,
                    "new_level": new_level,
                    "total_xp": record.xp,
                    "messages_count": record.messages_count,
                },
            )

        progress_pct = round((current_lvl_xp / max(needed_xp, 1)) * 100.0, 1)

        return {
            "guild_id": guild_id,
            "discord_user_id": str(user_id),
            "messages_count": record.messages_count,
            "total_xp": record.xp,
            "level": record.level,
            "current_level_xp": current_lvl_xp,
            "xp_needed_for_next": needed_xp,
            "progress_percent": progress_pct,
            "xp_gained": awarded_xp,
            "leveled_up": leveled_up,
            "old_level": old_level,
        }

    async def get_member_rank_card(self, guild_id: int, user_id: int) -> Dict[str, Any]:
        """Fetch rank card statistics for a member."""
        record = await self.level_repo.get_or_create_member_level(guild_id, user_id)
        rank = await self.level_repo.get_member_rank(guild_id, user_id)
        _, current_lvl_xp, needed_xp = calculate_level_from_xp(record.xp)
        progress_pct = round((current_lvl_xp / max(needed_xp, 1)) * 100.0, 1)

        return {
            "guild_id": guild_id,
            "discord_user_id": str(user_id),
            "rank": rank,
            "level": record.level,
            "total_xp": record.xp,
            "current_level_xp": current_lvl_xp,
            "xp_needed_for_next": needed_xp,
            "progress_percent": progress_pct,
            "messages_count": record.messages_count,
            "last_message_at": record.last_message_at.isoformat() if record.last_message_at else None,
        }

    async def get_xp_leaderboard(self, guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch the community XP and activity leaderboard."""
        records = await self.level_repo.get_leaderboard(guild_id, limit=limit)
        results = []
        for idx, r in enumerate(records, start=1):
            _, current_lvl_xp, needed_xp = calculate_level_from_xp(r.xp)
            results.append({
                "rank": idx,
                "discord_user_id": str(r.discord_user_id),
                "level": r.level,
                "total_xp": r.xp,
                "messages_count": r.messages_count,
                "progress_percent": round((current_lvl_xp / max(needed_xp, 1)) * 100.0, 1),
            })
        return results

    async def admin_adjust_xp(
        self,
        guild_id: int,
        officer_id: int,
        officer_roles: List[str] | str,
        target_user_id: int,
        xp_delta: int,
    ) -> Dict[str, Any]:
        """Admin/Officer manual adjustment of user XP."""
        if not has_sufficient_role(officer_roles, "officer"):
            raise LevelPermissionError("Only officers or higher can manually adjust member XP.")

        record = await self.level_repo.get_or_create_member_level(guild_id, target_user_id)
        record.xp = max(0, record.xp + xp_delta)
        new_level, _, _ = calculate_level_from_xp(record.xp)
        record.level = new_level
        await self.session.flush()

        await self.audit_repo.log_action(
            guild_id=guild_id,
            actor_id=officer_id,
            action="MEMBER_XP_ADJUSTED",
            target_entity="member_level",
            target_id=str(record.id),
            details={"target_user_id": str(target_user_id), "xp_delta": xp_delta, "new_xp": record.xp},
        )
        return await self.get_member_rank_card(guild_id, target_user_id)
