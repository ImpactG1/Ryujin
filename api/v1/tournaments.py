from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_claims, get_db_session, require_role
from services.tournament_service import (
    DuplicateRegistrationError,
    MatchDisputeError,
    TournamentFullError,
    TournamentNotFoundError,
    TournamentPermissionError,
    TournamentService,
    TournamentStateError,
)

router = APIRouter(tags=["Tournaments & Standings"])


class CreateTournamentRequest(BaseModel):
    title: str = Field(..., max_length=150)
    description: Optional[str] = None
    max_participants: int = Field(default=16, ge=2, le=128)


class ReportScorePayload(BaseModel):
    score1: int = Field(..., ge=0)
    score2: int = Field(..., ge=0)


class RaiseDisputePayload(BaseModel):
    reason: str = Field(..., min_length=5)


class ResolveDisputePayload(BaseModel):
    winner_id: int
    officer_notes: Optional[str] = None


class TournamentResponse(BaseModel):
    id: int
    guild_id: int
    title: str
    description: Optional[str]
    max_participants: int
    status: str


class MatchResponse(BaseModel):
    id: int
    tournament_id: int
    round_number: int
    match_number: int
    participant1_id: Optional[str]
    participant2_id: Optional[str]
    score1: int
    score2: int
    winner_id: Optional[str]
    status: str


class StandingResponse(BaseModel):
    rank: int
    discord_user_id: str
    status: str


@router.post("/guilds/{guild_id}/tournaments", response_model=TournamentResponse, status_code=status.HTTP_201_CREATED)
async def create_tournament(
    guild_id: int,
    body: CreateTournamentRequest,
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    service = TournamentService(session)
    user_id = int(claims.get("sub", 0))
    roles = claims.get("roles", [])
    try:
        t = await service.create_tournament(
            guild_id=guild_id,
            creator_id=user_id,
            creator_roles=roles,
            title=body.title,
            description=body.description,
            max_participants=body.max_participants,
        )
        return TournamentResponse(
            id=t.id,
            guild_id=t.guild_id,
            title=t.title,
            description=t.description,
            max_participants=t.max_participants,
            status=t.status,
        )
    except TournamentPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/guilds/{guild_id}/tournaments/{tournament_id}/register")
async def register_tournament(
    guild_id: int,
    tournament_id: int,
    claims: Dict[str, Any] = Depends(get_current_user_claims),
    session: AsyncSession = Depends(get_db_session),
):
    service = TournamentService(session)
    user_id = int(claims.get("sub", 0))
    try:
        part = await service.register_participant(tournament_id, user_id)
        return {
            "success": True,
            "tournament_id": tournament_id,
            "seed": part.seed,
            "discord_user_id": str(part.discord_user_id),
            "status": part.status,
        }
    except TournamentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DuplicateRegistrationError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except (TournamentFullError, TournamentStateError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/guilds/{guild_id}/tournaments/{tournament_id}/generate-bracket", response_model=List[MatchResponse])
async def generate_bracket(
    guild_id: int,
    tournament_id: int,
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    service = TournamentService(session)
    user_id = int(claims.get("sub", 0))
    roles = claims.get("roles", [])
    try:
        matches = await service.generate_single_elimination_bracket(
            tournament_id=tournament_id,
            initiator_id=user_id,
            initiator_roles=roles,
        )
        return [
            MatchResponse(
                id=m.id,
                tournament_id=m.tournament_id,
                round_number=m.round_number,
                match_number=m.match_number,
                participant1_id=str(m.participant1_id) if m.participant1_id else None,
                participant2_id=str(m.participant2_id) if m.participant2_id else None,
                score1=m.score1,
                score2=m.score2,
                winner_id=str(m.winner_id) if m.winner_id else None,
                status=m.status,
            )
            for m in matches
        ]
    except TournamentStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except TournamentPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get("/guilds/{guild_id}/tournaments/{tournament_id}/bracket", response_model=List[MatchResponse])
async def get_bracket(
    guild_id: int,
    tournament_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    service = TournamentService(session)
    matches = await service.list_matches(tournament_id)
    return [
        MatchResponse(
            id=m.id,
            tournament_id=m.tournament_id,
            round_number=m.round_number,
            match_number=m.match_number,
            participant1_id=str(m.participant1_id) if m.participant1_id else None,
            participant2_id=str(m.participant2_id) if m.participant2_id else None,
            score1=m.score1,
            score2=m.score2,
            winner_id=str(m.winner_id) if m.winner_id else None,
            status=m.status,
        )
        for m in matches
    ]


@router.post("/guilds/{guild_id}/tournaments/{tournament_id}/matches/{match_id}/score", response_model=MatchResponse)
async def report_score(
    guild_id: int,
    tournament_id: int,
    match_id: int,
    body: ReportScorePayload,
    claims: Dict[str, Any] = Depends(get_current_user_claims),
    session: AsyncSession = Depends(get_db_session),
):
    service = TournamentService(session)
    user_id = int(claims.get("sub", 0))
    roles = claims.get("roles", [])
    try:
        m = await service.report_match_score(
            match_id=match_id,
            reporter_id=user_id,
            reporter_roles=roles,
            score1=body.score1,
            score2=body.score2,
        )
        return MatchResponse(
            id=m.id,
            tournament_id=m.tournament_id,
            round_number=m.round_number,
            match_number=m.match_number,
            participant1_id=str(m.participant1_id) if m.participant1_id else None,
            participant2_id=str(m.participant2_id) if m.participant2_id else None,
            score1=m.score1,
            score2=m.score2,
            winner_id=str(m.winner_id) if m.winner_id else None,
            status=m.status,
        )
    except TournamentPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (TournamentStateError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/guilds/{guild_id}/tournaments/{tournament_id}/matches/{match_id}/dispute")
async def raise_dispute(
    guild_id: int,
    tournament_id: int,
    match_id: int,
    body: RaiseDisputePayload,
    claims: Dict[str, Any] = Depends(get_current_user_claims),
    session: AsyncSession = Depends(get_db_session),
):
    service = TournamentService(session)
    user_id = int(claims.get("sub", 0))
    try:
        disp = await service.raise_dispute(match_id, user_id, body.reason)
        return {"id": disp.id, "match_id": disp.match_id, "status": disp.status, "reason": disp.reason}
    except TournamentPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except MatchDisputeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/guilds/{guild_id}/tournaments/{tournament_id}/disputes/{dispute_id}/resolve")
async def resolve_dispute(
    guild_id: int,
    tournament_id: int,
    dispute_id: int,
    body: ResolveDisputePayload,
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    service = TournamentService(session)
    officer_id = int(claims.get("sub", 0))
    roles = claims.get("roles", [])
    try:
        disp = await service.resolve_dispute(
            dispute_id=dispute_id,
            officer_id=officer_id,
            officer_roles=roles,
            winner_id=body.winner_id,
            officer_notes=body.officer_notes,
        )
        return {"id": disp.id, "status": disp.status, "resolved_by": str(disp.resolved_by_id)}
    except TournamentPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (MatchDisputeError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/guilds/{guild_id}/tournaments/{tournament_id}/standings", response_model=List[StandingResponse])
async def get_tournament_standings(
    guild_id: int,
    tournament_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    service = TournamentService(session)
    return await service.calculate_standings(tournament_id)

