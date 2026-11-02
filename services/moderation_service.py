from datetime import datetime, timedelta, timezone
import json
from typing import Any, Dict, List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logger import logger, mask_pii_dict
from core.permissions import has_sufficient_role
from core.scheduler import scheduler
from models.member import Member
from models.moderation import AuditLog, ModerationSanction
from repositories.audit_repo import AuditRepository
from repositories.guild_repo import GuildRepository
from repositories.moderation_repo import ModerationRepository


class ModerationPermissionError(Exception):
    pass


class ModerationService:
    VALID_SANCTION_TYPES = {"warn", "mute", "kick", "ban"}

    def __init__(self, session: AsyncSession):
        self.session = session
        self.moderation_repo = ModerationRepository(session)
        self.guild_repo = GuildRepository(session)
        self.audit_repo = AuditRepository(session)

    async def apply_sanction(
        self,
        guild_id: int,
        moderator_id: int,
        moderator_roles: List[str] | str,
        target_user_id: int,
        sanction_type: str,
        reason: str,
        duration_minutes: Optional[int] = None,
    ) -> ModerationSanction:
        clean_type = sanction_type.strip().lower()
        if clean_type not in self.VALID_SANCTION_TYPES:
            raise ValueError(f"Invalid sanction type '{sanction_type}'. Must be one of {self.VALID_SANCTION_TYPES}")

        # Enforce officer+ role for sanctions
        if not has_sufficient_role(moderator_roles, "officer"):
            raise ModerationPermissionError("Only officers or higher can apply moderation sanctions.")

        await self.guild_repo.get_or_create_guild(guild_id)

        now = datetime.now(timezone.utc)
        expires_at = None
        if clean_type == "mute" and duration_minutes:
            expires_at = now + timedelta(minutes=duration_minutes)

        sanction = await self.moderation_repo.create_sanction(
            guild_id=guild_id,
            target_user_id=target_user_id,
            moderator_id=moderator_id,
            sanction_type=clean_type,
            reason=reason,
            duration_minutes=duration_minutes,
            expires_at=expires_at,
        )

        # Schedule automatic mute expiry job if APScheduler is running
        if clean_type == "mute" and duration_minutes and scheduler.running:
            job_id = f"mute_expiry_{sanction.id}"
            try:
                scheduler.add_job(
                    self.expire_mute,
                    "date",
                    run_date=expires_at,
                    args=[sanction.id],
                    id=job_id,
                    replace_existing=True,
                )
            except Exception as e:
                logger.warning("Could not schedule mute expiry job: %s", e)

        # Audit log
        await self.audit_repo.log_action(
            guild_id=guild_id,
            actor_id=moderator_id,
            action=f"SANCTION_{clean_type.upper()}",
            target_entity="member",
            target_id=str(target_user_id),
            details={
                "sanction_id": sanction.id,
                "reason": reason,
                "duration_minutes": duration_minutes,
                "expires_at": expires_at.isoformat() if expires_at else None,
            },
        )

        return sanction

    async def expire_mute(self, sanction_id: int) -> None:
        """Scheduled worker to automatically lift a mute upon expiry."""
        sanction = await self.moderation_repo.deactivate_sanction(sanction_id)
        if sanction:
            logger.info("Mute sanction #%s for user %s expired and deactivated.", sanction.id, sanction.target_user_id)
            await self.audit_repo.log_action(
                guild_id=sanction.guild_id,
                actor_id=0,  # System bot
                action="MUTE_EXPIRED",
                target_entity="member",
                target_id=str(sanction.target_user_id),
                details={"sanction_id": sanction.id},
            )

    async def get_audit_logs_with_role_pii_masking(
        self,
        guild_id: int,
        viewer_roles: List[str] | str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Return audit logs with role-based PII masking:
        - Admins and Owners see full data.
        - Officers / Moderators see partial data (PII like emails, tokens, and personal names are masked).
        """
        is_admin = has_sufficient_role(viewer_roles, "admin")
        logs = await self.moderation_repo.list_audit_logs(guild_id, limit=limit)

        result = []
        for l in logs:
            try:
                details = json.loads(l.details_json)
            except Exception:
                details = {}

            masked_details = mask_pii_dict(details, is_admin=is_admin)

            result.append({
                "id": l.id,
                "guild_id": l.guild_id,
                "actor_id": str(l.actor_id),
                "action": l.action,
                "target_entity": l.target_entity,
                "target_id": l.target_id,
                "details": masked_details,
                "created_at": l.created_at.isoformat(),
            })

        return result

    async def detect_anti_abuse_anomalies(self, guild_id: int) -> List[Dict[str, Any]]:
        """
        Anti-abuse anomaly detection engine:
        1. Checks for mass join anomalies (many joins within a 5-minute window).
        2. Checks for repeated sanctions anomaly (>= 3 sanctions in 24 hours).
        
        CRITICAL ARCHITECTURAL RULE:
        Flags for human review and NEVER auto-bans.
        """
        now = datetime.now(timezone.utc)
        anomalies = []

        # 1. Mass joins anomaly check (> 10 members joined in last 5 minutes)
        five_mins_ago = now - timedelta(minutes=5)
        stmt_joins = select(func.count(Member.id)).where(
            Member.guild_id == guild_id,
            Member.joined_at >= five_mins_ago,
        )
        res_joins = await self.session.execute(stmt_joins)
        recent_joins_count = res_joins.scalar_one() or 0

        if recent_joins_count >= 10:
            anomalies.append({
                "anomaly_type": "MASS_JOIN_SPIKE",
                "severity": "HIGH",
                "count": recent_joins_count,
                "window": "5m",
                "flagged_for_human_review": True,
                "action_taken": "FLAGGED_FOR_OFFICER_REVIEW",  # NEVER auto-ban!
                "message": f"Detected {recent_joins_count} joins in the last 5 minutes. Flagged for officer review.",
            })

        # 2. Repeated sanctions anomaly check (users with >= 3 sanctions in last 24h)
        twenty_four_hours_ago = now - timedelta(hours=24)
        stmt_repeated = (
            select(ModerationSanction.target_user_id, func.count(ModerationSanction.id).label("sanction_count"))
            .where(
                ModerationSanction.guild_id == guild_id,
                ModerationSanction.created_at >= twenty_four_hours_ago,
            )
            .group_by(ModerationSanction.target_user_id)
            .having(func.count(ModerationSanction.id) >= 3)
        )
        res_repeated = await self.session.execute(stmt_repeated)
        for row in res_repeated.all():
            u_id, count = row
            anomalies.append({
                "anomaly_type": "REPEATED_SANCTIONS_SPIKE",
                "severity": "MEDIUM",
                "target_user_id": str(u_id),
                "sanction_count": count,
                "window": "24h",
                "flagged_for_human_review": True,
                "action_taken": "FLAGGED_FOR_OFFICER_REVIEW",  # NEVER auto-ban!
                "message": f"User <@{u_id}> received {count} sanctions within 24 hours. Flagged for officer review.",
            })

        if anomalies:
            await self.audit_repo.log_action(
                guild_id=guild_id,
                actor_id=0,
                action="ANTI_ABUSE_ANOMALIES_FLAGGED",
                target_entity="moderation",
                target_id=str(guild_id),
                details={"anomalies_count": len(anomalies), "anomalies": anomalies},
            )

        return anomalies

