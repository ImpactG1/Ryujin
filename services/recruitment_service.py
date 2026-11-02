from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from core.logger import mask_pii_string
from core.permissions import has_sufficient_role
from models.recruitment import RecruitmentApplication
from repositories.audit_repo import AuditRepository
from repositories.guild_repo import GuildRepository
from repositories.member_repo import MemberRepository
from repositories.recruitment_repo import RecruitmentRepository


class RecruitmentPermissionError(Exception):
    pass


class ApplicationNotFoundError(Exception):
    pass


class InvalidApplicationStateError(Exception):
    pass


class RecruitmentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.recruitment_repo = RecruitmentRepository(session)
        self.member_repo = MemberRepository(session)
        self.guild_repo = GuildRepository(session)
        self.audit_repo = AuditRepository(session)

    async def submit_public_application(
        self,
        guild_id: int,
        discord_tag: str,
        email: str,
        full_name: str,
        experience: str,
        answers: Optional[Dict[str, Any]] = None,
        discord_user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Public recruitment submission (no auth required).
        Returns a sanitized response with all PII strictly stripped/masked.
        """
        await self.guild_repo.get_or_create_guild(guild_id)
        answers_str = json.dumps(answers or {})

        app = await self.recruitment_repo.create_application(
            guild_id=guild_id,
            discord_tag=discord_tag,
            email=email,
            full_name=full_name,
            experience=experience,
            answers_json=answers_str,
            discord_user_id=discord_user_id,
        )

        await self.audit_repo.log_action(
            guild_id=guild_id,
            actor_id=discord_user_id or 0,
            action="RECRUITMENT_APPLICATION_SUBMITTED",
            target_entity="recruitment_application",
            target_id=str(app.id),
            details={"discord_tag": discord_tag},
        )

        # Return sanitized public representation with PII stripped
        masked_name = f"{app.full_name[0]}***" if app.full_name else "[PROTECTED]"
        return {
            "id": app.id,
            "guild_id": app.guild_id,
            "discord_tag": app.discord_tag,
            "email": mask_pii_string(app.email),
            "full_name": masked_name,
            "experience": app.experience,
            "status": app.status,
            "created_at": app.created_at.isoformat(),
        }

    async def list_applications(
        self,
        guild_id: int,
        reviewer_roles: List[str] | str,
        status: Optional[str] = None,
    ) -> List[RecruitmentApplication]:
        if not has_sufficient_role(reviewer_roles, "officer"):
            raise RecruitmentPermissionError("Only officers or higher can view recruitment applications.")
        return await self.recruitment_repo.list_applications(guild_id=guild_id, status=status)

    async def review_application(
        self,
        application_id: int,
        reviewer_id: int,
        reviewer_roles: List[str] | str,
        decision: str,  # 'approved' or 'rejected'
    ) -> Dict[str, Any]:
        """
        Review an application. On approval:
        - Auto-provisions a member record in the community.
        - Writes an audit log entry.
        """
        if not has_sufficient_role(reviewer_roles, "officer"):
            raise RecruitmentPermissionError("Only officers or higher can review applications.")

        app = await self.recruitment_repo.get_application(application_id)
        if not app:
            raise ApplicationNotFoundError(f"Application {application_id} not found.")

        if app.status != "pending":
            raise InvalidApplicationStateError(f"Application is already {app.status}.")

        clean_decision = decision.strip().lower()
        now = datetime.now(timezone.utc)

        provisioned_member_id = None
        if clean_decision == "approved":
            app.status = "approved"
            target_user_id = app.discord_user_id or (100000000 + app.id)
            # Auto-provision community member record
            member = await self.member_repo.provision_member(
                guild_id=app.guild_id,
                user_id=target_user_id,
                username=app.discord_tag,
                display_name=app.full_name,
            )
            provisioned_member_id = str(member.discord_user_id)
        elif clean_decision == "rejected":
            app.status = "rejected"
        else:
            raise ValueError(f"Invalid decision: '{decision}'")

        app.reviewer_id = reviewer_id
        app.reviewed_at = now
        await self.session.flush()

        await self.audit_repo.log_action(
            guild_id=app.guild_id,
            actor_id=reviewer_id,
            action=f"RECRUITMENT_{clean_decision.upper()}",
            target_entity="recruitment_application",
            target_id=str(app.id),
            details={
                "applicant_tag": app.discord_tag,
                "provisioned_member_id": provisioned_member_id,
            },
        )

        return {
            "id": app.id,
            "status": app.status,
            "reviewer_id": str(reviewer_id),
            "reviewed_at": app.reviewed_at.isoformat(),
            "auto_provisioned_member_id": provisioned_member_id,
        }
