from typing import Any, Dict, List
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_claims, get_db_session
from services.checkin_service import CheckInService

router = APIRouter(tags=["Attendance & Check-Ins"])


class CheckInRequest(BaseModel):
    user_id: int | None = Field(default=None, description="Optional target user ID if called by admin/bot")


class CheckInResponse(BaseModel):
    success: bool
    already_checked_in: bool
    streak_count: int
    longest_streak: int
    checkin_date: str
    message: str


class LeaderboardEntry(BaseModel):
    user_id: str
    current_streak: int
    longest_streak: int
    last_checkin_date: str | None


class UserStreakResponse(BaseModel):
    user_id: str
    current_streak: int
    longest_streak: int
    last_checkin_date: str | None


@router.post("/guilds/{guild_id}/checkin", response_model=CheckInResponse)
async def post_checkin(
    guild_id: int,
    body: CheckInRequest = CheckInRequest(),
    claims: Dict[str, Any] = Depends(get_current_user_claims),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Record a daily check-in for the authenticated user (or specified user for admin).
    Idempotent: repeating the check-in on the same day returns the existing record without double-counting.
    """
    user_id = body.user_id if body.user_id else int(claims.get("sub", 0))
    service = CheckInService(session)
    result = await service.process_checkin(guild_id=guild_id, user_id=user_id)
    return result


@router.get("/guilds/{guild_id}/streaks/leaderboard", response_model=List[LeaderboardEntry])
async def get_streak_leaderboard(
    guild_id: int,
    limit: int = Query(default=10, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get the top check-in streaks for a guild.
    """
    service = CheckInService(session)
    return await service.get_streak_leaderboard(guild_id=guild_id, limit=limit)


@router.get("/guilds/{guild_id}/members/{user_id}/streak", response_model=UserStreakResponse)
async def get_member_streak(
    guild_id: int,
    user_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get the streak statistics for a specific guild member.
    """
    service = CheckInService(session)
    return await service.get_user_streak(guild_id=guild_id, user_id=user_id)

