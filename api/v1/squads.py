from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_claims, get_db_session, require_role
from services.squad_service import (
    AlreadyMemberError,
    InvalidRequestStateError,
    PendingRequestExistsError,
    SquadFullError,
    SquadNotFoundError,
    SquadPermissionError,
    SquadService,
)

router = APIRouter(tags=["Squads Lifecycle"])


class CreateSquadRequest(BaseModel):
    name: str = Field(..., max_length=100)
    captain_id: int
    capacity: int = Field(default=10, ge=1, le=100)


class ReviewRequestPayload(BaseModel):
    decision: str = Field(..., pattern="^(approved|rejected)$")
    notes: Optional[str] = None


class SquadResponse(BaseModel):
    id: int
    guild_id: int
    name: str
    captain_id: str
    capacity: int


class JoinRequestResponse(BaseModel):
    id: int
    squad_id: int
    discord_user_id: str
    status: str
    reviewer_id: Optional[str]
    reviewed_at: Optional[str]
    notes: Optional[str]


@router.post("/guilds/{guild_id}/squads", response_model=SquadResponse, status_code=status.HTTP_201_CREATED)
async def create_squad(
    guild_id: int,
    body: CreateSquadRequest,
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    service = SquadService(session)
    user_id = int(claims.get("sub", 0))
    roles = claims.get("roles", [])
    try:
        squad = await service.create_squad(
            guild_id=guild_id,
            creator_id=user_id,
            creator_roles=roles,
            name=body.name,
            captain_id=body.captain_id,
            capacity=body.capacity,
        )
        return SquadResponse(
            id=squad.id,
            guild_id=squad.guild_id,
            name=squad.name,
            captain_id=str(squad.captain_id),
            capacity=squad.capacity,
        )
    except SquadPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get("/guilds/{guild_id}/squads", response_model=List[SquadResponse])
async def list_squads(
    guild_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    service = SquadService(session)
    squads = await service.list_squads(guild_id)
    return [
        SquadResponse(
            id=s.id,
            guild_id=s.guild_id,
            name=s.name,
            captain_id=str(s.captain_id),
            capacity=s.capacity,
        )
        for s in squads
    ]


@router.post("/guilds/{guild_id}/squads/{squad_id}/join-requests", response_model=JoinRequestResponse, status_code=status.HTTP_201_CREATED)
async def request_join_squad(
    guild_id: int,
    squad_id: int,
    claims: Dict[str, Any] = Depends(get_current_user_claims),
    session: AsyncSession = Depends(get_db_session),
):
    service = SquadService(session)
    user_id = int(claims.get("sub", 0))
    try:
        req = await service.request_to_join(squad_id=squad_id, user_id=user_id)
        return JoinRequestResponse(
            id=req.id,
            squad_id=req.squad_id,
            discord_user_id=str(req.discord_user_id),
            status=req.status,
            reviewer_id=str(req.reviewer_id) if req.reviewer_id else None,
            reviewed_at=req.reviewed_at.isoformat() if req.reviewed_at else None,
            notes=req.notes,
        )
    except SquadNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except SquadFullError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except (AlreadyMemberError, PendingRequestExistsError) as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/guilds/{guild_id}/squads/{squad_id}/join-requests/{request_id}/review", response_model=JoinRequestResponse)
async def review_join_request(
    guild_id: int,
    squad_id: int,
    request_id: int,
    body: ReviewRequestPayload,
    claims: Dict[str, Any] = Depends(get_current_user_claims),
    session: AsyncSession = Depends(get_db_session),
):
    service = SquadService(session)
    user_id = int(claims.get("sub", 0))
    roles = claims.get("roles", [])
    try:
        req = await service.review_join_request(
            request_id=request_id,
            reviewer_id=user_id,
            reviewer_roles=roles,
            decision=body.decision,
            notes=body.notes,
        )
        return JoinRequestResponse(
            id=req.id,
            squad_id=req.squad_id,
            discord_user_id=str(req.discord_user_id),
            status=req.status,
            reviewer_id=str(req.reviewer_id) if req.reviewer_id else None,
            reviewed_at=req.reviewed_at.isoformat() if req.reviewed_at else None,
            notes=req.notes,
        )
    except SquadPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except InvalidRequestStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except SquadFullError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/guilds/{guild_id}/squads/{squad_id}/stats")
async def get_squad_stats(
    guild_id: int,
    squad_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    service = SquadService(session)
    try:
        return await service.get_squad_attendance_stats(squad_id)
    except SquadNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

