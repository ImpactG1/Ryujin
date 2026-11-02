from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_claims, get_db_session, require_role
from services.event_service import (
    EventAttendanceWindowError,
    EventNotFoundError,
    EventPermissionError,
    EventService,
)

router = APIRouter(tags=["Events & Reminders"])


class CreateEventRequest(BaseModel):
    title: str = Field(..., max_length=150)
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    target_squad_id: Optional[int] = None


class UpdateEventRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    target_squad_id: Optional[int] = None


class EventResponse(BaseModel):
    id: int
    guild_id: int
    title: str
    description: Optional[str]
    start_time: str
    end_time: str
    creator_id: int
    target_squad_id: Optional[int]
    status: str


class AttendanceResponse(BaseModel):
    success: bool
    already_marked: bool
    status: str
    marked_at: str
    message: str


def _serialize_event(e) -> EventResponse:
    return EventResponse(
        id=e.id,
        guild_id=e.guild_id,
        title=e.title,
        description=e.description,
        start_time=e.start_time.isoformat(),
        end_time=e.end_time.isoformat(),
        creator_id=e.creator_id,
        target_squad_id=e.target_squad_id,
        status=e.status,
    )


@router.post("/guilds/{guild_id}/events", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    guild_id: int,
    body: CreateEventRequest,
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    service = EventService(session)
    user_id = int(claims.get("sub", 0))
    roles = claims.get("roles", [])
    try:
        event = await service.create_event(
            guild_id=guild_id,
            creator_id=user_id,
            creator_roles=roles,
            title=body.title,
            start_time=body.start_time,
            end_time=body.end_time,
            description=body.description,
            target_squad_id=body.target_squad_id,
        )
        return _serialize_event(event)
    except EventPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get("/guilds/{guild_id}/events", response_model=List[EventResponse])
async def list_events(
    guild_id: int,
    event_status: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
):
    service = EventService(session)
    events = await service.list_events(guild_id=guild_id, status=event_status, limit=limit)
    return [_serialize_event(e) for e in events]


@router.get("/guilds/{guild_id}/events/{event_id}", response_model=EventResponse)
async def get_event(
    guild_id: int,
    event_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    service = EventService(session)
    event = await service.get_event(event_id)
    if not event or event.guild_id != guild_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    return _serialize_event(event)


@router.patch("/guilds/{guild_id}/events/{event_id}", response_model=EventResponse)
async def update_event(
    guild_id: int,
    event_id: int,
    body: UpdateEventRequest,
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    service = EventService(session)
    user_id = int(claims.get("sub", 0))
    roles = claims.get("roles", [])
    try:
        event = await service.update_event(
            event_id=event_id,
            editor_id=user_id,
            editor_roles=roles,
            title=body.title,
            start_time=body.start_time,
            end_time=body.end_time,
            description=body.description,
            target_squad_id=body.target_squad_id,
        )
        return _serialize_event(event)
    except EventNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except EventPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.delete("/guilds/{guild_id}/events/{event_id}", response_model=EventResponse)
async def cancel_event(
    guild_id: int,
    event_id: int,
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    service = EventService(session)
    user_id = int(claims.get("sub", 0))
    roles = claims.get("roles", [])
    try:
        event = await service.cancel_event(
            event_id=event_id,
            canceller_id=user_id,
            canceller_roles=roles,
        )
        return _serialize_event(event)
    except EventNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except EventPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/guilds/{guild_id}/events/{event_id}/attend", response_model=AttendanceResponse)
async def attend_event(
    guild_id: int,
    event_id: int,
    claims: Dict[str, Any] = Depends(get_current_user_claims),
    session: AsyncSession = Depends(get_db_session),
):
    service = EventService(session)
    user_id = int(claims.get("sub", 0))
    try:
        result = await service.record_attendance(event_id=event_id, user_id=user_id)
        return result
    except EventNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except EventAttendanceWindowError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

