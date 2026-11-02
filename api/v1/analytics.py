from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_claims, get_db_session, require_role
from services.analytics_service import AnalyticsService

router = APIRouter(tags=["Dashboard & Analytics"])


class MembersOverview(BaseModel):
    total: int
    active: int


class AttendanceOverview(BaseModel):
    active_streaks: int
    average_streak: float


class NextEventSummary(BaseModel):
    id: int
    title: str
    start_time: str


class EventsOverview(BaseModel):
    upcoming_count: int
    next_events: List[NextEventSummary]


class OpenRequestsOverview(BaseModel):
    recruitment_applications: int
    leave_requests: int
    total_open: int


class ModerationOverview(BaseModel):
    active_sanctions_count: int
    breakdown: Dict[str, int]


class TournamentsOverview(BaseModel):
    active_tournaments: int


class AnalyticsOverviewResponse(BaseModel):
    guild_id: int
    members: MembersOverview
    attendance: AttendanceOverview
    events: EventsOverview
    open_requests: OpenRequestsOverview
    moderation: ModerationOverview
    tournaments: TournamentsOverview


class PaginatedMembersResponse(BaseModel):
    items: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int
    total_pages: int


@router.get("/guilds/{guild_id}/analytics/overview", response_model=AnalyticsOverviewResponse)
async def get_guild_analytics_overview(
    guild_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get aggregated dashboard metrics for Next.js frontend:
    - Member counts
    - Active check-in streaks & averages
    - Upcoming events
    - Open recruitment and leave requests
    - Moderation sanctions
    - Tournament summaries
    """
    service = AnalyticsService(session)
    return await service.get_overview(guild_id)


@router.get("/analytics/overview", response_model=AnalyticsOverviewResponse)
async def get_general_analytics_overview(
    guild_id: int = Query(default=123456789012345678, description="Guild ID to inspect"),
    session: AsyncSession = Depends(get_db_session),
):
    """General dashboard overview route."""
    service = AnalyticsService(session)
    return await service.get_overview(guild_id)


@router.get("/guilds/{guild_id}/members", response_model=PaginatedMembersResponse)
async def get_paginated_members(
    guild_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None),
    active_only: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
):
    """Paginated, searchable community members list for dashboard tables."""
    service = AnalyticsService(session)
    return await service.list_members_paginated(
        guild_id=guild_id,
        page=page,
        page_size=page_size,
        search=search,
        active_only=active_only,
    )

