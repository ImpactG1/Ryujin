from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_claims, get_db_session, require_role
from services.moderation_service import ModerationPermissionError, ModerationService

router = APIRouter(tags=["Moderation & Anti-Abuse"])


class CreateSanctionRequest(BaseModel):
    target_user_id: int
    sanction_type: str = Field(..., pattern="^(warn|mute|kick|ban)$")
    reason: str = Field(..., min_length=3)
    duration_minutes: Optional[int] = Field(None, ge=1)


class SanctionResponse(BaseModel):
    id: int
    guild_id: int
    target_user_id: str
    moderator_id: str
    sanction_type: str
    reason: str
    duration_minutes: Optional[int]
    expires_at: Optional[str]
    is_active: bool


@router.post("/guilds/{guild_id}/moderation/sanctions", response_model=SanctionResponse, status_code=status.HTTP_201_CREATED)
async def apply_sanction(
    guild_id: int,
    body: CreateSanctionRequest,
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    service = ModerationService(session)
    moderator_id = int(claims.get("sub", 0))
    roles = claims.get("roles", [])
    try:
        sanction = await service.apply_sanction(
            guild_id=guild_id,
            moderator_id=moderator_id,
            moderator_roles=roles,
            target_user_id=body.target_user_id,
            sanction_type=body.sanction_type,
            reason=body.reason,
            duration_minutes=body.duration_minutes,
        )
        return SanctionResponse(
            id=sanction.id,
            guild_id=sanction.guild_id,
            target_user_id=str(sanction.target_user_id),
            moderator_id=str(sanction.moderator_id),
            sanction_type=sanction.sanction_type,
            reason=sanction.reason,
            duration_minutes=sanction.duration_minutes,
            expires_at=sanction.expires_at.isoformat() if sanction.expires_at else None,
            is_active=sanction.is_active,
        )
    except ModerationPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/guilds/{guild_id}/moderation/sanctions", response_model=List[SanctionResponse])
async def list_sanctions(
    guild_id: int,
    target_user_id: Optional[int] = Query(None),
    active_only: bool = Query(False),
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    service = ModerationService(session)
    sanctions = await service.moderation_repo.list_sanctions(
        guild_id=guild_id, target_user_id=target_user_id, active_only=active_only
    )
    return [
        SanctionResponse(
            id=s.id,
            guild_id=s.guild_id,
            target_user_id=str(s.target_user_id),
            moderator_id=str(s.moderator_id),
            sanction_type=s.sanction_type,
            reason=s.reason,
            duration_minutes=s.duration_minutes,
            expires_at=s.expires_at.isoformat() if s.expires_at else None,
            is_active=s.is_active,
        )
        for s in sanctions
    ]


@router.get("/guilds/{guild_id}/audit-logs")
async def get_audit_logs(
    guild_id: int,
    limit: int = Query(50, ge=1, le=100),
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get audit logs with role-based PII masking:
    - Admins see full unmasked PII.
    - Officers/Moderators see masked PII.
    """
    service = ModerationService(session)
    roles = claims.get("roles", [])
    return await service.get_audit_logs_with_role_pii_masking(guild_id=guild_id, viewer_roles=roles, limit=limit)


@router.get("/guilds/{guild_id}/moderation/anomalies")
async def get_anti_abuse_anomalies(
    guild_id: int,
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Evaluate real-time anti-abuse anomalies (mass joins, repeated sanctions).
    Flags suspicious behavior for human review and NEVER auto-bans.
    """
    service = ModerationService(session)
    return await service.detect_anti_abuse_anomalies(guild_id)

