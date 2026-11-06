from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_claims, get_db_session, require_role
from services.level_service import LevelPermissionError, LevelRankError, LevelService

router = APIRouter(tags=["Levels & Activity EXP Tracker"])


class RankCardResponse(BaseModel):
    guild_id: int
    discord_user_id: str
    rank: int
    rank_tier: str  # D, C, B, A, S, SS, SSS
    previous_rank_tier: Optional[str] = None
    rank_updated_at: Optional[str] = None
    shy_quote: str
    level: int
    total_xp: int
    current_level_xp: int
    xp_needed_for_next: int
    progress_percent: float
    messages_count: int
    last_message_at: Optional[str] = None


class LeaderboardRankEntry(BaseModel):
    rank: int
    discord_user_id: str
    rank_tier: str
    level: int
    total_xp: int
    messages_count: int
    progress_percent: float


class AdjustXPRequest(BaseModel):
    xp_delta: int = Field(..., description="Amount of XP to add (positive) or deduct (negative)")


class RankChangeRequest(BaseModel):
    target_tier: Optional[str] = Field(None, description="Optional target rank tier (D, C, B, A, S, SS, SSS)")
    reason: Optional[str] = Field(None, description="Reason for promotion or demotion")


class RankSyncRequest(BaseModel):
    discord_tier: str = Field(..., description="Rank tier detected from Discord role (D, C, B, A, S, SS, SSS)")


class RankHistoryEntry(BaseModel):
    id: int
    from_tier: str
    to_tier: str
    change_type: str
    actor_id: str
    reason: Optional[str] = None
    created_at: str


@router.get("/guilds/{guild_id}/members/{user_id}/rank", response_model=RankCardResponse)
async def get_member_rank(
    guild_id: int,
    user_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    """Fetch member rank card, letter rank tier (D..SSS), and Ryujin's shy 1-line quote."""
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


@router.post("/guilds/{guild_id}/members/{user_id}/rank/promote", response_model=RankCardResponse)
async def promote_member_rank(
    guild_id: int,
    user_id: int,
    body: RankChangeRequest,
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    """Officer endpoint to manually promote a member's rank tier (e.g. D -> C -> B -> A -> S -> SS -> SSS)."""
    service = LevelService(session)
    officer_id = int(claims.get("sub", 0))
    roles = claims.get("roles", [])
    try:
        return await service.promote_member(
            guild_id=guild_id,
            officer_id=officer_id,
            officer_roles=roles,
            target_user_id=user_id,
            target_tier=body.target_tier,
            reason=body.reason,
        )
    except LevelPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except LevelRankError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/guilds/{guild_id}/members/{user_id}/rank/demote", response_model=RankCardResponse)
async def demote_member_rank(
    guild_id: int,
    user_id: int,
    body: RankChangeRequest,
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    """Officer endpoint to manually demote a member's rank tier."""
    service = LevelService(session)
    officer_id = int(claims.get("sub", 0))
    roles = claims.get("roles", [])
    try:
        return await service.demote_member(
            guild_id=guild_id,
            officer_id=officer_id,
            officer_roles=roles,
            target_user_id=user_id,
            target_tier=body.target_tier,
            reason=body.reason,
        )
    except LevelPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except LevelRankError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/guilds/{guild_id}/members/{user_id}/rank/history", response_model=List[RankHistoryEntry])
async def get_member_rank_history(
    guild_id: int,
    user_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
):
    """Fetch complete promotion and demotion audit trail for a member."""
    service = LevelService(session)
    return await service.get_rank_history(guild_id, user_id, limit=limit)


@router.post("/guilds/{guild_id}/members/{user_id}/rank/sync", response_model=RankCardResponse)
async def sync_discord_rank_tier(
    guild_id: int,
    user_id: int,
    body: RankSyncRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Sync member rank tier when detected from Discord roles."""
    service = LevelService(session)
    try:
        return await service.sync_discord_rank(guild_id, user_id, body.discord_tier)
    except LevelRankError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
