from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_claims, get_db_session, require_role
from services.recognition_service import (
    AchievementNotFoundError,
    DuplicateAwardError,
    RecognitionPermissionError,
    RecognitionService,
)

router = APIRouter(tags=["Recognition & MOTM"])


class CreateAchievementRequest(BaseModel):
    code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=100)
    description: str
    criteria_type: str = Field(..., description="'streak' or 'events_attended'")
    threshold: int = Field(..., ge=1)
    badge_icon: Optional[str] = None


class AchievementResponse(BaseModel):
    id: int
    guild_id: int
    code: str
    name: str
    description: str
    criteria_type: str
    threshold: int
    badge_icon: Optional[str]


class AchievementProgressResponse(BaseModel):
    achievement_id: int
    code: str
    name: str
    description: str
    criteria_type: str
    threshold: int
    badge_icon: Optional[str]
    current_value: int
    percentage: float
    is_unlocked: bool
    awarded_at: Optional[str]


class AwardRequest(BaseModel):
    target_user_id: int


class AwardResponse(BaseModel):
    id: int
    guild_id: int
    discord_user_id: str
    achievement_id: int
    awarded_at: str


class CrownMOTMRequest(BaseModel):
    year_month: str = Field(..., pattern=r"^\d{4}-\d{2}$", description="Format: YYYY-MM")
    target_user_id: int
    reason: str


class MOTMResponse(BaseModel):
    id: int
    guild_id: int
    year_month: str
    discord_user_id: str
    reason: str
    crowned_by: str
    awarded_at: str


@router.post("/guilds/{guild_id}/achievements", response_model=AchievementResponse, status_code=status.HTTP_201_CREATED)
async def create_achievement(
    guild_id: int,
    body: CreateAchievementRequest,
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    service = RecognitionService(session)
    roles = claims.get("roles", [])
    try:
        ach = await service.create_achievement(
            guild_id=guild_id,
            creator_roles=roles,
            code=body.code,
            name=body.name,
            description=body.description,
            criteria_type=body.criteria_type,
            threshold=body.threshold,
            badge_icon=body.badge_icon,
        )
        return AchievementResponse(
            id=ach.id,
            guild_id=ach.guild_id,
            code=ach.code,
            name=ach.name,
            description=ach.description,
            criteria_type=ach.criteria_type,
            threshold=ach.threshold,
            badge_icon=ach.badge_icon,
        )
    except RecognitionPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get("/guilds/{guild_id}/members/{user_id}/achievements/progress", response_model=List[AchievementProgressResponse])
async def get_member_achievements_progress(
    guild_id: int,
    user_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    service = RecognitionService(session)
    return await service.get_user_progress(guild_id=guild_id, user_id=user_id)


@router.post("/guilds/{guild_id}/achievements/{achievement_id}/award", response_model=AwardResponse)
async def award_achievement(
    guild_id: int,
    achievement_id: int,
    body: AwardRequest,
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    service = RecognitionService(session)
    officer_id = int(claims.get("sub", 0))
    try:
        award = await service.award_achievement(
            guild_id=guild_id,
            user_id=body.target_user_id,
            achievement_id=achievement_id,
            awarded_by=officer_id,
        )
        return AwardResponse(
            id=award.id,
            guild_id=award.guild_id,
            discord_user_id=str(award.discord_user_id),
            achievement_id=award.achievement_id,
            awarded_at=award.awarded_at.isoformat(),
        )
    except DuplicateAwardError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except AchievementNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/guilds/{guild_id}/motm", response_model=MOTMResponse)
async def crown_motm(
    guild_id: int,
    body: CrownMOTMRequest,
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    service = RecognitionService(session)
    officer_id = int(claims.get("sub", 0))
    roles = claims.get("roles", [])
    try:
        record = await service.crown_motm(
            guild_id=guild_id,
            crowned_by_id=officer_id,
            crowned_by_roles=roles,
            year_month=body.year_month,
            target_user_id=body.target_user_id,
            reason=body.reason,
        )
        return MOTMResponse(
            id=record.id,
            guild_id=record.guild_id,
            year_month=record.year_month,
            discord_user_id=str(record.discord_user_id),
            reason=record.reason,
            crowned_by=str(record.crowned_by),
            awarded_at=record.awarded_at.isoformat(),
        )
    except RecognitionPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get("/guilds/{guild_id}/motm/history", response_model=List[MOTMResponse])
async def get_motm_history(
    guild_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    service = RecognitionService(session)
    records = await service.get_motm_history(guild_id)
    return [
        MOTMResponse(
            id=r.id,
            guild_id=r.guild_id,
            year_month=r.year_month,
            discord_user_id=str(r.discord_user_id),
            reason=r.reason,
            crowned_by=str(r.crowned_by),
            awarded_at=r.awarded_at.isoformat(),
        )
        for r in records
    ]
