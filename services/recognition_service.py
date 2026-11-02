from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from core.permissions import has_sufficient_role
from models.recognition import Achievement, MemberAward, MOTMRecord
from repositories.audit_repo import AuditRepository
from repositories.checkin_repo import CheckInRepository
from repositories.guild_repo import GuildRepository
from repositories.recognition_repo import RecognitionRepository


class DuplicateAwardError(Exception):
    pass


class AchievementNotFoundError(Exception):
    pass


class RecognitionPermissionError(Exception):
    pass


class RecognitionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.recognition_repo = RecognitionRepository(session)
        self.checkin_repo = CheckInRepository(session)
        self.guild_repo = GuildRepository(session)
        self.audit_repo = AuditRepository(session)

    async def create_achievement(
        self,
        guild_id: int,
        creator_roles: List[str] | str,
        code: str,
        name: str,
        description: str,
        criteria_type: str,
        threshold: int,
        badge_icon: Optional[str] = None,
    ) -> Achievement:
        if not has_sufficient_role(creator_roles, "officer"):
            raise RecognitionPermissionError("Only officers or higher can create achievements.")

        await self.guild_repo.get_or_create_guild(guild_id)
        ach = await self.recognition_repo.create_achievement(
            guild_id=guild_id,
            code=code,
            name=name,
            description=description,
            criteria_type=criteria_type,
            threshold=threshold,
            badge_icon=badge_icon,
        )
        return ach

    async def get_user_progress(self, guild_id: int, user_id: int) -> List[Dict[str, Any]]:
        """
        Calculate transparent progress for all achievements in a guild for a specific member.
        Shows exact current stat, target threshold, percentage, and unlock status.
        """
        achievements = await self.recognition_repo.list_achievements(guild_id)
        awards = await self.recognition_repo.list_user_awards(guild_id, user_id)
        awarded_map = {a.achievement_id: a for a in awards}

        # Retrieve relevant user stats
        streak = await self.checkin_repo.get_or_create_streak(guild_id, user_id)
        max_streak = max(streak.current_streak, streak.longest_streak)
        events_attended = await self.recognition_repo.count_events_attended(user_id)

        progress_list = []
        for ach in achievements:
            if ach.criteria_type == "streak":
                current_val = max_streak
            elif ach.criteria_type == "events_attended":
                current_val = events_attended
            else:
                current_val = 0

            is_unlocked = ach.id in awarded_map
            percentage = 100.0 if is_unlocked else min(100.0, round((current_val / max(ach.threshold, 1)) * 100.0, 1))

            award_record = awarded_map.get(ach.id)
            progress_list.append({
                "achievement_id": ach.id,
                "code": ach.code,
                "name": ach.name,
                "description": ach.description,
                "criteria_type": ach.criteria_type,
                "threshold": ach.threshold,
                "badge_icon": ach.badge_icon,
                "current_value": current_val,
                "percentage": percentage,
                "is_unlocked": is_unlocked,
                "awarded_at": award_record.awarded_at.isoformat() if award_record else None,
            })

        return progress_list

    async def award_achievement(
        self,
        guild_id: int,
        user_id: int,
        achievement_id: int,
        awarded_by: Optional[int] = None,
    ) -> MemberAward:
        """
        Awards an achievement to a member.
        Enforces duplicate award protection: raises DuplicateAwardError (409 Conflict) if already awarded.
        """
        achievement = await self.recognition_repo.get_achievement(achievement_id)
        if not achievement or achievement.guild_id != guild_id:
            raise AchievementNotFoundError(f"Achievement {achievement_id} not found in this guild.")

        existing = await self.recognition_repo.get_award(guild_id, user_id, achievement_id)
        if existing:
            raise DuplicateAwardError(
                f"Achievement '{achievement.code}' has already been awarded to member {user_id}."
            )

        award = await self.recognition_repo.create_award(
            guild_id=guild_id,
            user_id=user_id,
            achievement_id=achievement_id,
            awarded_by=awarded_by,
        )

        await self.audit_repo.log_action(
            guild_id=guild_id,
            actor_id=awarded_by or user_id,
            action="ACHIEVEMENT_AWARD",
            target_entity="achievement",
            target_id=str(achievement.id),
            details={"recipient_id": str(user_id), "code": achievement.code},
        )
        return award

    async def check_and_auto_award_eligible(self, guild_id: int, user_id: int) -> List[MemberAward]:
        """Auto-evaluates eligible achievements and awards them if not already unlocked."""
        progress_items = await self.get_user_progress(guild_id, user_id)
        newly_awarded = []
        for item in progress_items:
            if not item["is_unlocked"] and item["current_value"] >= item["threshold"]:
                try:
                    award = await self.award_achievement(
                        guild_id=guild_id,
                        user_id=user_id,
                        achievement_id=item["achievement_id"],
                        awarded_by=None,
                    )
                    newly_awarded.append(award)
                except DuplicateAwardError:
                    pass
        return newly_awarded

    async def crown_motm(
        self,
        guild_id: int,
        crowned_by_id: int,
        crowned_by_roles: List[str] | str,
        year_month: str,
        target_user_id: int,
        reason: str,
    ) -> MOTMRecord:
        if not has_sufficient_role(crowned_by_roles, "officer"):
            raise RecognitionPermissionError("Only officers or higher can crown Member of the Month.")

        await self.guild_repo.get_or_create_guild(guild_id)
        record = await self.recognition_repo.crown_motm(
            guild_id=guild_id,
            year_month=year_month,
            user_id=target_user_id,
            reason=reason,
            crowned_by=crowned_by_id,
        )

        await self.audit_repo.log_action(
            guild_id=guild_id,
            actor_id=crowned_by_id,
            action="MOTM_CROWN",
            target_entity="motm",
            target_id=year_month,
            details={"target_user_id": str(target_user_id), "reason": reason},
        )
        return record

    async def get_motm_history(self, guild_id: int) -> List[MOTMRecord]:
        return await self.recognition_repo.get_motm_history(guild_id)

