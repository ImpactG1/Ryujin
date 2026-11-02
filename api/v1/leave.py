from datetime import date
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_claims, get_db_session, require_role
from services.leave_service import LeaveConflictError, LeaveNotFoundError, LeavePermissionError, LeaveService

router = APIRouter(tags=["Leave Management"])


class CreateLeaveRequest(BaseModel):
    start_date: date
    end_date: date
    reason: str = Field(..., min_length=3)


class ReviewLeavePayload(BaseModel):
    decision: str = Field(..., pattern="^(approved|rejected)$")


class ConflictingEventSummary(BaseModel):
    id: int
    title: str
    start_time: str


class LeaveResponse(BaseModel):
    id: int
    guild_id: int
    discord_user_id: str
    start_date: str
    end_date: str
    reason: str
    status: str
    conflicting_events: List[ConflictingEventSummary] = []


class LeaveReviewResponse(BaseModel):
    id: int
    status: str
    reviewer_id: str
    reviewed_at: str


@router.post("/guilds/{guild_id}/leave-requests", response_model=LeaveResponse, status_code=status.HTTP_201_CREATED)
async def submit_leave_request(
    guild_id: int,
    body: CreateLeaveRequest,
    claims: Dict[str, Any] = Depends(get_current_user_claims),
    session: AsyncSession = Depends(get_db_session),
):
    service = LeaveService(session)
    user_id = int(claims.get("sub", 0))
    try:
        return await service.submit_leave_request(
            guild_id=guild_id,
            user_id=user_id,
            start_date=body.start_date,
            end_date=body.end_date,
            reason=body.reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except LeaveConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/guilds/{guild_id}/leave-requests")
async def list_leave_requests(
    guild_id: int,
    req_status: Optional[str] = Query(None, alias="status"),
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    service = LeaveService(session)
    leaves = await service.list_leave_requests(guild_id, status=req_status)
    return [
        {
            "id": l.id,
            "guild_id": l.guild_id,
            "discord_user_id": str(l.discord_user_id),
            "start_date": str(l.start_date),
            "end_date": str(l.end_date),
            "reason": l.reason,
            "status": l.status,
        }
        for l in leaves
    ]


@router.post("/guilds/{guild_id}/leave-requests/{leave_id}/review", response_model=LeaveReviewResponse)
async def review_leave_request(
    guild_id: int,
    leave_id: int,
    body: ReviewLeavePayload,
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    service = LeaveService(session)
    officer_id = int(claims.get("sub", 0))
    roles = claims.get("roles", [])
    try:
        return await service.review_leave_request(
            leave_id=leave_id,
            reviewer_id=officer_id,
            reviewer_roles=roles,
            decision=body.decision,
        )
    except LeaveNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except LeavePermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

