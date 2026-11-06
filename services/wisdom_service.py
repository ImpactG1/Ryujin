from datetime import date, datetime, timezone
import hashlib
import random
from typing import Any, Dict, List, Optional
import zoneinfo
from sqlalchemy.ext.asyncio import AsyncSession

from models.base import utc_now
from repositories.audit_repo import AuditRepository
from repositories.guild_repo import GuildRepository
from repositories.wisdom_repo import WisdomRepository

CURATED_WISDOM_QUOTES = [
    "A tree that never faces the wind will never know how strong its roots are.",
    "Your lack of consistency is a shame for people who believe in you.",
    "A blade that isn't sharpened every day dulls before the battle even begins.",
    "Discipline is choosing between what you want now and what you want most.",
    "The master has failed more times than the beginner has even tried.",
    "Silence is not weakness; it is the calm before the strike.",
    "The pain of discipline weighs ounces; the pain of regret weighs tons.",
    "Even the darkest shadows cannot extinguish a flame that refuses to die.",
    "Do not pray for an easy life; pray for the strength to endure a difficult one.",
    "He who conquers himself is the mightiest warrior.",
    "A warrior does not seek victory without struggle, for hollow triumphs yield no growth.",
    "Excuses will always be waiting for you. Opportunity will not.",
    "Iron is forged only through heat and relentless hammering.",
    "You do not rise to the level of your goals; you fall to the level of your discipline.",
    "The summit seems impossible only to those who stare from the base without walking.",
    "Small daily improvements over time lead to stunning results.",
    "Comfort is the silent thief of potential.",
    "A smooth sea never made a skilled sailor.",
]


class WisdomService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.wisdom_repo = WisdomRepository(session)
        self.guild_repo = GuildRepository(session)
        self.audit_repo = AuditRepository(session)

    async def get_guild_current_date(self, guild_id: int, custom_utc_time: Optional[datetime] = None) -> date:
        """Calculate today's date in the guild's configured display timezone (default Asia/Kolkata)."""
        tz_str = await self.guild_repo.get_guild_timezone(guild_id)
        try:
            tz = zoneinfo.ZoneInfo(tz_str)
        except Exception:
            tz = zoneinfo.ZoneInfo("Asia/Kolkata")

        utc_time = custom_utc_time or datetime.now(timezone.utc)
        return utc_time.astimezone(tz).date()

    def select_daily_quote(self, guild_id: int, target_date: date) -> str:
        """Deterministic yet rotating quote selection per day per guild from curated bank."""
        seed_str = f"{guild_id}:{target_date.isoformat()}"
        hash_val = int(hashlib.sha256(seed_str.encode()).hexdigest(), 16)
        index = hash_val % len(CURATED_WISDOM_QUOTES)
        return CURATED_WISDOM_QUOTES[index]

    async def get_or_unlock_daily_wisdom(
        self,
        guild_id: int,
        user_id: int,
        current_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Unlock today's server wisdom quote:
        - Can be triggered by anyone.
        - Enforces strictly ONCE per day in the whole server.
        - If already unlocked today, returns the existing quote and the member who unlocked it.
        """
        await self.guild_repo.get_or_create_guild(guild_id)
        local_date = await self.get_guild_current_date(guild_id, current_time)

        # 1. Check if already unlocked for today in this guild
        existing = await self.wisdom_repo.get_wisdom_by_date(guild_id, local_date)
        if existing:
            return {
                "already_unlocked": True,
                "quote": existing.quote,
                "author": existing.author,
                "unlocked_by_user_id": str(existing.unlocked_by_user_id),
                "unlocked_at": existing.unlocked_at.isoformat(),
                "date": str(existing.date),
                "shy_quote": f"...Today's wisdom was already unlocked by <@{existing.unlocked_by_user_id}>. Reflect on it.",
            }

        # 2. Select today's wisdom quote
        quote = self.select_daily_quote(guild_id, local_date)
        author = "Ryujin"

        # 3. Atomically persist today's unlock
        record = await self.wisdom_repo.create_wisdom(
            guild_id=guild_id,
            target_date=local_date,
            quote=quote,
            author=author,
            user_id=user_id,
        )

        # 4. Audit log entry
        await self.audit_repo.log_action(
            guild_id=guild_id,
            actor_id=user_id,
            action="DAILY_WISDOM_UNLOCKED",
            target_entity="daily_wisdom",
            target_id=str(record.id),
            details={
                "date": str(local_date),
                "quote": quote,
                "author": author,
            },
        )
        await self.session.flush()

        return {
            "already_unlocked": False,
            "quote": record.quote,
            "author": record.author,
            "unlocked_by_user_id": str(record.unlocked_by_user_id),
            "unlocked_at": record.unlocked_at.isoformat(),
            "date": str(record.date),
            "shy_quote": "...Today's wisdom has been revealed. Take it to heart, okay?",
        }

    async def get_today_wisdom(
        self,
        guild_id: int,
        current_time: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch today's wisdom if it has been unlocked, else return None."""
        await self.guild_repo.get_or_create_guild(guild_id)
        local_date = await self.get_guild_current_date(guild_id, current_time)
        existing = await self.wisdom_repo.get_wisdom_by_date(guild_id, local_date)
        if not existing:
            return None
        return {
            "quote": existing.quote,
            "author": existing.author,
            "unlocked_by_user_id": str(existing.unlocked_by_user_id),
            "unlocked_at": existing.unlocked_at.isoformat(),
            "date": str(existing.date),
        }

    async def get_wisdom_history(
        self,
        guild_id: int,
        limit: int = 15,
    ) -> List[Dict[str, Any]]:
        """Fetch past unlocked wisdom quotes for the dashboard."""
        records = await self.wisdom_repo.get_recent_wisdoms(guild_id, limit=limit)
        return [
            {
                "id": r.id,
                "date": str(r.date),
                "quote": r.quote,
                "author": r.author,
                "unlocked_by_user_id": str(r.unlocked_by_user_id),
                "unlocked_at": r.unlocked_at.isoformat(),
            }
            for r in records
        ]

