from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_claims, get_db_session, require_role
from services.ai_service import AIService

router = APIRouter(tags=["Ryujin Brain (Groq AI)"])


class AIChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    channel_id: Optional[int] = Field(default=1000000000)


class AIChatResponse(BaseModel):
    reply: str


class ModAssistRequest(BaseModel):
    violation_text: str = Field(..., min_length=1)


class DisputeAssistRequest(BaseModel):
    match_info: str
    participant1_claim: str
    participant2_claim: str


@router.post("/guilds/{guild_id}/ai/chat", response_model=AIChatResponse)
async def ai_chat(
    guild_id: int,
    body: AIChatRequest,
    claims: Dict[str, Any] = Depends(get_current_user_claims),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Chat with Ryujin Brain powered by Groq.
    Incorporates user ID persona, anti-injection, and function calling for server stats.
    """
    user_id = int(claims.get("sub", 0))
    service = AIService(session)
    reply = await service.chat(
        channel_id=body.channel_id or 1000000000,
        user_id=user_id,
        guild_id=guild_id,
        user_message=body.message,
    )
    return AIChatResponse(reply=reply)


@router.get("/guilds/{guild_id}/ai/summary")
async def get_ai_community_summary(
    guild_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Generate an AI-powered digest summarizing real attendance, event, and tournament stats.
    """
    service = AIService(session)
    summary = await service.generate_community_summary(guild_id)
    return {"guild_id": guild_id, "summary": summary}


@router.post("/guilds/{guild_id}/ai/mod-assist")
async def ai_moderation_assist(
    guild_id: int,
    body: ModAssistRequest,
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    """Officer-only AI assistant that suggests (never executes) a sanction severity."""
    service = AIService(session)
    return await service.moderation_assist(body.violation_text)


@router.post("/guilds/{guild_id}/ai/dispute-assist")
async def ai_dispute_assist(
    guild_id: int,
    body: DisputeAssistRequest,
    claims: Dict[str, Any] = Depends(require_role("officer")),
    session: AsyncSession = Depends(get_db_session),
):
    """Officer-only AI assistant that summarizes both sides of a tournament dispute."""
    service = AIService(session)
    summary = await service.dispute_assist(
        match_info=body.match_info,
        p1_claim=body.participant1_claim,
        p2_claim=body.participant2_claim,
    )
    return {"summary": summary}

