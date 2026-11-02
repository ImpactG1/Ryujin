from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import zoneinfo
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.audit_repo import AuditRepository
from repositories.checkin_repo import CheckInRepository
from repositories.guild_repo import GuildRepository


class CheckInService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.checkin_repo = CheckInRepository(session)
        self.guild_repo = GuildRepository(session)
        self.audit_repo = AuditRepository(session)

    async def get_guild_current_date(self, guild_id: int, custom_utc_time: Optional[datetime] = None) -> date:
        tz_str = await self.guild_repo.get_guild_timezone(guild_id)
        try:
            tz = zoneinfo.ZoneInfo(tz_str)
        except Exception:
            tz = zoneinfo.ZoneInfo("Asia/Kolkata")

        utc_time = custom_utc_time or datetime.now(timezone.utc)
        return utc_time.astimezone(tz).date()

    async def process_checkin(
        self,
        guild_id: int,
        user_id: int,
        current_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Process a user check-in idempotently:
        - If already checked in on the guild's local date, returns the existing record.
        - If checked in yesterday, increments the streak.
        - If missed yesterday or first time, resets streak to 1.
        - Records an audit log entry.
        """
        await self.guild_repo.get_or_create_guild(guild_id)
        local_date = await self.get_guild_current_date(guild_id, current_time)

        # 1. Check for existing check-in today (Idempotency)
        existing_checkin = await self.checkin_repo.get_checkin(guild_id, user_id, local_date)
        streak_record = await self.checkin_repo.get_or_create_streak(guild_id, user_id)

        if existing_checkin:
            return {
                "success": True,
                "already_checked_in": True,
                "streak_count": streak_record.current_streak,
                "longest_streak": streak_record.longest_streak,
                "checkin_date": str(local_date),
                "message": f"Already checked in today! Your streak is {streak_record.current_streak} days.",
            }

        # 2. Calculate new streak
        yesterday = local_date - timedelta(days=1)
        if streak_record.last_checkin_date == yesterday:
            new_streak = streak_record.current_streak + 1
        else:
            new_streak = 1

        streak_record.current_streak = new_streak
        streak_record.longest_streak = max(streak_record.longest_streak, new_streak)
        streak_record.last_checkin_date = local_date

        # 3. Create checkin record
        checkin_obj = await self.checkin_repo.create_checkin(
            guild_id=guild_id,
            user_id=user_id,
            checkin_date=local_date,
            streak_count=new_streak,
        )

        # 4. Audit logging
        await self.audit_repo.log_action(
            guild_id=guild_id,
            actor_id=user_id,
            action="MEMBER_CHECKIN",
            target_entity="checkin",
            target_id=str(checkin_obj.id),
            details={
                "streak": new_streak,
                "longest_streak": streak_record.longest_streak,
                "date": str(local_date),
            },
        )

        return {
            "success": True,
            "already_checked_in": False,
            "streak_count": new_streak,
            "longest_streak": streak_record.longest_streak,
            "checkin_date": str(local_date),
            "message": f"Check-in successful! Your streak is now {new_streak} days.",
        }

    async def get_streak_leaderboard(self, guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        records = await self.checkin_repo.get_leaderboard(guild_id, limit=limit)
        return [
            {
                "user_id": str(r.discord_user_id),
                "current_streak": r.current_streak,
                "longest_streak": r.longest_streak,
                "last_checkin_date": str(r.last_checkin_date) if r.last_checkin_date else None,
            }
            for r in records
        ]

    async def get_user_streak(self, guild_id: int, user_id: int) -> Dict[str, Any]:
        streak = await self.checkin_repo.get_or_create_streak(guild_id, user_id)
        return {
            "user_id": str(streak.discord_user_id),
            "current_streak": streak.current_streak,
            "longest_streak": streak.longest_streak,
            "last_checkin_date": str(streak.last_checkin_date) if streak.last_checkin_date else None,
        }

