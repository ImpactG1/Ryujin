from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_claims, get_db_session, require_role
from services.level_service import LevelPermissionError, LevelService

router = APIRouter(tags=["Levels & Activity EXP Tracker"])


class RankCardResponse(BaseModel):
    guild_id: int
    discord_user_id: str
    rank: int
    level: int
    total_xp: int
    current_level_xp: int
    xp_needed_for_next: int
    progress_percent: float
    messages_count: int
    last_message_at: Optional[str]


class LeaderboardRankEntry(BaseModel):
    rank: int
    discord_user_id: str
    level: int
    total_xp: int
    messages_count: int
    progress_percent: float


class AdjustXPRequest(BaseModel):
    xp_delta: int = Field(..., description="Amount of XP to add (positive) or deduct (negative)")


@router.get("/guilds/{guild_id}/members/{user_id}/rank", response_model=RankCardResponse)
async def get_member_rank(
    guild_id: int,
    user_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    """Fetch rank card, current level, progress, and message count for a member."""
    service = LevelService(session)
    return await service.get_member_rank_card(guild_id, user_id)


@router.get("/guilds/{guild_id}/levels/leaderboard", response_model=List[LeaderboardRankEntry])
async def get_levels_leaderboard(
    guild_id: int,
    limit: int = Query(default=10, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
):
    """Fetch community level & message activity leaderboard."""
    service = LevelService(session)
    return await service.get_xp_leaderboard(guild_id, limit=limit)


@router.post("/guilds/{guild_id}/members/{user_id}/xp", response_model=RankCardResponse)
async def adjust_member_xp(
    guild_id: int,
    user_id: int,
    body: AdjustXPRequest,
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    """Officer endpoint to manually grant or deduct member experience points."""
    service = LevelService(session)
    officer_id = int(claims.get("sub", 0))
    roles = claims.get("roles", [])
    try:
        return await service.admin_adjust_xp(
            guild_id=guild_id,
            officer_id=officer_id,
            officer_roles=roles,
            target_user_id=user_id,
            xp_delta=body.xp_delta,
        )
    except LevelPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
