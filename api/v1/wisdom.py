from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_claims, get_db_session
from services.wisdom_service import WisdomService

router = APIRouter(tags=["Daily Wisdom"])


class WisdomResponse(BaseModel):
    already_unlocked: bool
    quote: str
    author: str
    unlocked_by_user_id: str
    unlocked_at: str
    date: str
    shy_quote: str


class TodayWisdomStatus(BaseModel):
    unlocked: bool
    data: Optional[Dict[str, Any]] = None


class UnlockWisdomRequest(BaseModel):
    user_id: int


class WisdomHistoryItem(BaseModel):
    id: int
    date: str
    quote: str
    author: str
    unlocked_by_user_id: str
    unlocked_at: str


@router.get("/guilds/{guild_id}/wisdom/today", response_model=TodayWisdomStatus)
async def get_today_wisdom(
    guild_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    """Fetch today's unlocked wisdom for the guild, if any."""
    service = WisdomService(session)
    result = await service.get_today_wisdom(guild_id)
    if not result:
        return TodayWisdomStatus(unlocked=False, data=None)
    return TodayWisdomStatus(unlocked=True, data=result)


@router.post("/guilds/{guild_id}/wisdom/unlock", response_model=WisdomResponse)
async def unlock_daily_wisdom(
    guild_id: int,
    body: UnlockWisdomRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Unlock today's server wisdom quote.
    Can be triggered by anyone, but only once per day for the entire server.
    """
    service = WisdomService(session)
    result = await service.get_or_unlock_daily_wisdom(guild_id=guild_id, user_id=body.user_id)
    return result


@router.get("/guilds/{guild_id}/wisdom/history", response_model=List[WisdomHistoryItem])
async def get_wisdom_history(
    guild_id: int,
    limit: int = Query(default=15, ge=1, le=50),
    session: AsyncSession = Depends(get_db_session),
):
    """Fetch past unlocked wisdom quotes for the community dashboard."""
    service = WisdomService(session)
    return await service.get_wisdom_history(guild_id=guild_id, limit=limit)

