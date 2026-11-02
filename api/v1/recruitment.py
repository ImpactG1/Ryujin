from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_claims, get_db_session, require_role
from services.recruitment_service import (
    ApplicationNotFoundError,
    InvalidApplicationStateError,
    RecruitmentPermissionError,
    RecruitmentService,
)

router = APIRouter(tags=["Recruitment"])


class PublicApplicationRequest(BaseModel):
    discord_tag: str = Field(..., max_length=100)
    email: EmailStr
    full_name: str = Field(..., max_length=150)
    experience: str
    answers: Optional[Dict[str, Any]] = None
    discord_user_id: Optional[int] = None


class PublicApplicationResponse(BaseModel):
    id: int
    guild_id: int
    discord_tag: str
    email: str
    full_name: str
    experience: str
    status: str
    created_at: str


class ReviewApplicationRequest(BaseModel):
    decision: str = Field(..., pattern="^(approved|rejected)$")


class ApplicationReviewResponse(BaseModel):
    id: int
    status: str
    reviewer_id: str
    reviewed_at: str
    auto_provisioned_member_id: Optional[str]


@router.post(
    "/guilds/{guild_id}/recruitment/apply",
    response_model=PublicApplicationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Public application submission (No auth required)",
)
async def submit_application(
    guild_id: int,
    body: PublicApplicationRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Public recruitment application endpoint.
    Anyone can apply without a Discord Bearer token.
    All sensitive PII (email, full name) is stripped / masked from the response.
    """
    service = RecruitmentService(session)
    result = await service.submit_public_application(
        guild_id=guild_id,
        discord_tag=body.discord_tag,
        email=body.email,
        full_name=body.full_name,
        experience=body.experience,
        answers=body.answers,
        discord_user_id=body.discord_user_id,
    )
    return result


@router.get("/guilds/{guild_id}/recruitment/applications")
async def list_applications(
    guild_id: int,
    app_status: Optional[str] = Query(None, alias="status"),
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    """Officer-only endpoint to view recruitment applications."""
    service = RecruitmentService(session)
    roles = claims.get("roles", [])
    try:
        apps = await service.list_applications(guild_id=guild_id, reviewer_roles=roles, status=app_status)
        return [
            {
                "id": a.id,
                "discord_tag": a.discord_tag,
                "email": a.email,
                "full_name": a.full_name,
                "experience": a.experience,
                "status": a.status,
                "discord_user_id": str(a.discord_user_id) if a.discord_user_id else None,
                "created_at": a.created_at.isoformat(),
            }
            for a in apps
        ]
    except RecruitmentPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/guilds/{guild_id}/recruitment/applications/{application_id}/review", response_model=ApplicationReviewResponse)
async def review_application(
    guild_id: int,
    application_id: int,
    body: ReviewApplicationRequest,
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Officer review of application.
    On approval, automatically provisions a community member record.
    """
    service = RecruitmentService(session)
    user_id = int(claims.get("sub", 0))
    roles = claims.get("roles", [])
    try:
        return await service.review_application(
            application_id=application_id,
            reviewer_id=user_id,
            reviewer_roles=roles,
            decision=body.decision,
        )
    except ApplicationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidApplicationStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RecruitmentPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

