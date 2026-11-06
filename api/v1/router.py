from fastapi import APIRouter
from api.v1.ai import router as ai_router
from api.v1.analytics import router as analytics_router
from api.v1.checkin import router as checkin_router
from api.v1.events import router as events_router
from api.v1.leave import router as leave_router
from api.v1.levels import router as levels_router
from api.v1.moderation import router as moderation_router
from api.v1.recognition import router as recognition_router
from api.v1.recruitment import router as recruitment_router
from api.v1.squads import router as squads_router
from api.v1.tournaments import router as tournaments_router

api_router = APIRouter()
api_router.include_router(checkin_router)
api_router.include_router(events_router)
api_router.include_router(recognition_router)
api_router.include_router(squads_router)
api_router.include_router(recruitment_router)
api_router.include_router(leave_router)
api_router.include_router(tournaments_router)
api_router.include_router(moderation_router)
api_router.include_router(analytics_router)
api_router.include_router(levels_router)
api_router.include_router(ai_router)
