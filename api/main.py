from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.v1.router import api_router
from core.config import settings
from core.database import close_db, init_db
from core.logger import logger
from core.scheduler import shutdown_scheduler, start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Ryujin Backend API...")
    await init_db()
    start_scheduler()
    yield
    logger.info("Shutting down Ryujin Backend API...")
    shutdown_scheduler()
    await close_db()


app = FastAPI(
    title="Ryujin Community Management API",
    description="Backend API and Groq AI Layer for Ryujin Discord Bot & Next.js Dashboard",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS Configuration for Next.js dashboard (http://localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error_type": "ValidationError", "detail": exc.errors(), "status_code": 422},
    )


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_type": "HTTPException", "detail": exc.detail, "status_code": exc.status_code},
        headers=exc.headers,
    )


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok", "app": "Ryujin", "version": "1.0.0"}


# Mount versioned API routes
app.include_router(api_router, prefix="/api/v1")
