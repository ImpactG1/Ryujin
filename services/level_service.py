from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.permissions import has_sufficient_role
from models.base import utc_now
from models.level import MemberLevel
from repositories.audit_repo import AuditRepository
from repositories.guild_repo import GuildRepository
from repositories.level_repo import LevelRepository

RANK_TIERS = ["D", "C", "B", "A", "S", "SS", "SSS"]
RANK_TIER_INDEX = {tier: idx for idx, tier in enumerate(RANK_TIERS)}


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


def get_rank_tier_from_level(level: int) -> str:
    """Determine the Hunter/Server rank tier (D, C, B, A, S, SS, SSS) from user level."""
    if level >= 100:
        return "SSS"
    elif level >= 75:
        return "SS"
    elif level >= 50:
        return "S"
    elif level >= 30:
        return "A"
    elif level >= 15:
        return "B"
    elif level >= 5:
        return "C"
    return "D"


def generate_shy_rank_dialogue(
    rank_tier: str,
    user_id: int,
    change_type: Optional[str] = None,
    from_tier: Optional[str] = None,
) -> str:
    """
    Ryujin's shy, terse, man-of-few-words dialogue for member rank.
    Strictly 1 sentence / 1 line.
    """
    is_owner = (int(user_id) == int(settings.OWNER_DISCORD_ID))

    if is_owner:
        if change_type == "PROMOTION":
            return f"...Rank {rank_tier}. Boss, you got promoted... don't let it get to your head."
        return f"...Rank {rank_tier}. Boss, you're at the top... just don't slack off, okay?"

    if change_type == "PROMOTION" and from_tier:
        return f"...Promoted from {from_tier} to Rank {rank_tier}. *looks away* Keep it up."
    elif change_type == "DEMOTION" and from_tier:
        return f"...Demoted from {from_tier} to Rank {rank_tier}. Don't give up, okay?"

    tier_quotes = {
        "D": "...Rank D. Don't worry, everyone starts somewhere.",
        "C": "Rank C... You're making progress. Slowly.",
        "B": "Rank B... Not bad, I suppose.",
        "A": "Rank A. Keep this up and you might actually impress me.",
        "S": "Rank S... You're genuinely strong. *looks away*",
        "SS": "Rank SS... Truly terrifying power.",
        "SSS": "Rank SSS... Standing at the pinnacle.",
    }
    return tier_quotes.get(rank_tier, f"...Rank {rank_tier}.")


class LevelPermissionError(Exception):
    pass


class LevelRankError(Exception):
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
        - Calculates current level and triggers level-up.
        - Checks for automatic rank tier promotions (D -> C -> B -> A -> S -> SS -> SSS).
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

        # 4. Check for automatic rank promotion
        calculated_tier = get_rank_tier_from_level(new_level)
        current_tier_idx = RANK_TIER_INDEX.get(record.rank_tier, 0)
        calc_tier_idx = RANK_TIER_INDEX.get(calculated_tier, 0)

        rank_promoted = False
        if calc_tier_idx > current_tier_idx:
            old_tier = record.rank_tier
            record.previous_rank_tier = old_tier
            record.rank_tier = calculated_tier
            record.rank_updated_at = now
            rank_promoted = True

            await self.level_repo.record_rank_change(
                guild_id=guild_id,
                user_id=user_id,
                from_tier=old_tier,
                to_tier=calculated_tier,
                change_type="PROMOTION",
                actor_id=0,
                reason=f"Auto-promotion on reaching Level {new_level}",
            )

        await self.session.flush()

        # 5. Audit log on level up
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
                    "rank_tier": record.rank_tier,
                    "rank_promoted": rank_promoted,
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
            "rank_tier": record.rank_tier,
            "rank_promoted": rank_promoted,
            "current_level_xp": current_lvl_xp,
            "xp_needed_for_next": needed_xp,
            "progress_percent": progress_pct,
            "xp_gained": awarded_xp,
            "leveled_up": leveled_up,
            "old_level": old_level,
        }

    async def get_member_rank_card(self, guild_id: int, user_id: int) -> Dict[str, Any]:
        """Fetch rank card statistics, letter rank tier, and Ryujin's shy 1-line quote."""
        record = await self.level_repo.get_or_create_member_level(guild_id, user_id)
        rank_num = await self.level_repo.get_member_rank(guild_id, user_id)
        _, current_lvl_xp, needed_xp = calculate_level_from_xp(record.xp)
        progress_pct = round((current_lvl_xp / max(needed_xp, 1)) * 100.0, 1)

        latest_change = await self.level_repo.get_latest_rank_change(guild_id, user_id)
        change_type = latest_change.change_type if latest_change else None
        from_tier = latest_change.from_tier if latest_change else None

        shy_quote = generate_shy_rank_dialogue(
            rank_tier=record.rank_tier,
            user_id=user_id,
            change_type=change_type,
            from_tier=from_tier,
        )

        return {
            "guild_id": guild_id,
            "discord_user_id": str(user_id),
            "rank": rank_num,
            "rank_tier": record.rank_tier,
            "previous_rank_tier": record.previous_rank_tier,
            "rank_updated_at": record.rank_updated_at.isoformat() if record.rank_updated_at else None,
            "shy_quote": shy_quote,
            "level": record.level,
            "total_xp": record.xp,
            "current_level_xp": current_lvl_xp,
            "xp_needed_for_next": needed_xp,
            "progress_percent": progress_pct,
            "messages_count": record.messages_count,
            "last_message_at": record.last_message_at.isoformat() if record.last_message_at else None,
        }

    async def sync_discord_rank(self, guild_id: int, user_id: int, discord_tier: str) -> Dict[str, Any]:
        """
        Synchronize member rank tier when detected from Discord roles (e.g. D, C, B, A, S, SS, SSS).
        Automatically tracks promotions and demotions.
        """
        tier = discord_tier.strip().upper()
        if tier not in RANK_TIER_INDEX:
            raise LevelRankError(f"Invalid rank tier '{discord_tier}'. Valid tiers are: {', '.join(RANK_TIERS)}")

        record = await self.level_repo.get_or_create_member_level(guild_id, user_id)
        old_tier = record.rank_tier

        if old_tier != tier:
            old_idx = RANK_TIER_INDEX.get(old_tier, 0)
            new_idx = RANK_TIER_INDEX.get(tier, 0)
            change_type = "PROMOTION" if new_idx > old_idx else "DEMOTION"

            record.previous_rank_tier = old_tier
            record.rank_tier = tier
            record.rank_updated_at = utc_now()

            await self.level_repo.record_rank_change(
                guild_id=guild_id,
                user_id=user_id,
                from_tier=old_tier,
                to_tier=tier,
                change_type=change_type,
                actor_id=0,
                reason="Discord role synchronization",
            )
            await self.session.flush()

        return await self.get_member_rank_card(guild_id, user_id)

    async def promote_member(
        self,
        guild_id: int,
        officer_id: int,
        officer_roles: List[str] | str,
        target_user_id: int,
        target_tier: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Officer manual promotion to the next or specified rank tier."""
        if not has_sufficient_role(officer_roles, "officer"):
            raise LevelPermissionError("Only officers or higher can promote members.")

        record = await self.level_repo.get_or_create_member_level(guild_id, target_user_id)
        current_idx = RANK_TIER_INDEX.get(record.rank_tier, 0)

        if target_tier:
            new_tier = target_tier.strip().upper()
            if new_tier not in RANK_TIER_INDEX:
                raise LevelRankError(f"Invalid rank tier '{target_tier}'.")
            new_idx = RANK_TIER_INDEX[new_tier]
            if new_idx <= current_idx:
                raise LevelRankError(f"Target tier '{new_tier}' must be higher than current tier '{record.rank_tier}' for a promotion.")
        else:
            if current_idx >= len(RANK_TIERS) - 1:
                raise LevelRankError("Member is already at the maximum rank tier (SSS).")
            new_tier = RANK_TIERS[current_idx + 1]

        old_tier = record.rank_tier
        record.previous_rank_tier = old_tier
        record.rank_tier = new_tier
        record.rank_updated_at = utc_now()

        await self.level_repo.record_rank_change(
            guild_id=guild_id,
            user_id=target_user_id,
            from_tier=old_tier,
            to_tier=new_tier,
            change_type="PROMOTION",
            actor_id=officer_id,
            reason=reason or "Officer promotion",
        )
        await self.audit_repo.log_action(
            guild_id=guild_id,
            actor_id=officer_id,
            action="MEMBER_RANK_PROMOTED",
            target_entity="member_level",
            target_id=str(record.id),
            details={"target_user_id": str(target_user_id), "from_tier": old_tier, "to_tier": new_tier, "reason": reason},
        )
        await self.session.flush()
        return await self.get_member_rank_card(guild_id, target_user_id)

    async def demote_member(
        self,
        guild_id: int,
        officer_id: int,
        officer_roles: List[str] | str,
        target_user_id: int,
        target_tier: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Officer manual demotion to lower or specified rank tier."""
        if not has_sufficient_role(officer_roles, "officer"):
            raise LevelPermissionError("Only officers or higher can demote members.")

        record = await self.level_repo.get_or_create_member_level(guild_id, target_user_id)
        current_idx = RANK_TIER_INDEX.get(record.rank_tier, 0)

        if target_tier:
            new_tier = target_tier.strip().upper()
            if new_tier not in RANK_TIER_INDEX:
                raise LevelRankError(f"Invalid rank tier '{target_tier}'.")
            new_idx = RANK_TIER_INDEX[new_tier]
            if new_idx >= current_idx:
                raise LevelRankError(f"Target tier '{new_tier}' must be lower than current tier '{record.rank_tier}' for a demotion.")
        else:
            if current_idx <= 0:
                raise LevelRankError("Member is already at the lowest rank tier (D).")
            new_tier = RANK_TIERS[current_idx - 1]

        old_tier = record.rank_tier
        record.previous_rank_tier = old_tier
        record.rank_tier = new_tier
        record.rank_updated_at = utc_now()

        await self.level_repo.record_rank_change(
            guild_id=guild_id,
            user_id=target_user_id,
            from_tier=old_tier,
            to_tier=new_tier,
            change_type="DEMOTION",
            actor_id=officer_id,
            reason=reason or "Officer demotion",
        )
        await self.audit_repo.log_action(
            guild_id=guild_id,
            actor_id=officer_id,
            action="MEMBER_RANK_DEMOTED",
            target_entity="member_level",
            target_id=str(record.id),
            details={"target_user_id": str(target_user_id), "from_tier": old_tier, "to_tier": new_tier, "reason": reason},
        )
        await self.session.flush()
        return await self.get_member_rank_card(guild_id, target_user_id)

    async def get_rank_history(self, guild_id: int, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve promotion/demotion history for a member."""
        history = await self.level_repo.get_rank_history(guild_id, user_id, limit=limit)
        return [
            {
                "id": h.id,
                "from_tier": h.from_tier,
                "to_tier": h.to_tier,
                "change_type": h.change_type,
                "actor_id": str(h.actor_id),
                "reason": h.reason,
                "created_at": h.created_at.isoformat(),
            }
            for h in history
        ]

    async def get_xp_leaderboard(self, guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch the community XP and activity leaderboard."""
        records = await self.level_repo.get_leaderboard(guild_id, limit=limit)
        results = []
        for idx, r in enumerate(records, start=1):
            _, current_lvl_xp, needed_xp = calculate_level_from_xp(r.xp)
            results.append({
                "rank": idx,
                "discord_user_id": str(r.discord_user_id),
                "rank_tier": r.rank_tier,
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

        # Check if rank tier changes based on level
        calc_tier = get_rank_tier_from_level(new_level)
        if calc_tier != record.rank_tier:
            record.previous_rank_tier = record.rank_tier
            record.rank_tier = calc_tier
            record.rank_updated_at = utc_now()

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
