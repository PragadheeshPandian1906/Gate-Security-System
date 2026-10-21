"""
SmartGuard AI — FastAPI Application Entry Point
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.logging_config import configure_logging
from app.api.routes import auth, admin, health, people, vehicles, ai_verify
from app.api.routes import access, gate, schedule, watchlist
from app.api.routes import alerts, reports, contacts, notifications
from app.api.routes import visitors

# Initialise logging before anything else
configure_logging()
logger = logging.getLogger("smartguard.app")

settings = get_settings()


# ---------------------------------------------------------------------------
# Lifespan context manager (replaces deprecated on_event)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(
        "smartguard.app Application startup — %s [%s]",
        settings.app_name,
        settings.app_env,
    )

    try:
        settings.validate_critical()
        logger.info("smartguard.app Configuration validated successfully")
    except ValueError as exc:
        logger.error("smartguard.app Configuration error: %s", exc)

    # Capture main event loop for IoT singleton
    import asyncio
    from app.services.iot_service import iot_manager

    iot_manager.set_loop(asyncio.get_running_loop())

    # Initialize AI models before the app starts accepting requests
    from app.services import face_service, alpr_service

    logger.info("smartguard.app Initializing AI models at startup")

    face_ready = face_service.initialize_face_model()
    alpr_ready = alpr_service.initialize_alpr_model()

    logger.info(
        "smartguard.app AI startup status | face_ready=%s | alpr_ready=%s",
        face_ready,
        alpr_ready,
    )

    if not face_ready:
        logger.error("smartguard.app Face recognition is unavailable")

    if not alpr_ready:
        logger.error("smartguard.app Number-plate recognition is unavailable")

    yield

    # Shutdown
    logger.info("smartguard.app Application shutdown")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
app = FastAPI(
    title=settings.app_name,
    version="3.0.0",
    description="SmartGuard AI — Campus Security Management System (Phase 3)",
    lifespan=lifespan,
    docs_url=f"{settings.api_prefix}/docs" if settings.is_development else None,
    redoc_url=f"{settings.api_prefix}/redoc" if settings.is_development else None,
    openapi_url=f"{settings.api_prefix}/openapi.json" if settings.is_development else None,
)

# ---------------------------------------------------------------------------
# CORS — allow the configured Vite frontend origins only
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)
app.include_router(health.router, prefix=settings.api_prefix)
# Phase 2 routes
app.include_router(people.router, prefix=settings.api_prefix)
app.include_router(vehicles.router, prefix=settings.api_prefix)
app.include_router(ai_verify.router, prefix=settings.api_prefix)
# Phase 3 routes
app.include_router(access.router, prefix=settings.api_prefix)
app.include_router(gate.router, prefix=settings.api_prefix)
app.include_router(schedule.router, prefix=settings.api_prefix)
app.include_router(watchlist.router, prefix=settings.api_prefix)
# Phase 4 routes
app.include_router(alerts.router, prefix=settings.api_prefix)
app.include_router(reports.router, prefix=settings.api_prefix)
app.include_router(contacts.router, prefix=settings.api_prefix)
app.include_router(notifications.router, prefix=settings.api_prefix)
# Phase 5 routes
app.include_router(visitors.router, prefix=settings.api_prefix)

from typing import Optional
from fastapi import WebSocket, Query
from app.api.routes.gate import websocket_dashboard_monitor


# ---------------------------------------------------------------------------
# IoT WebSocket Endpoints
# ---------------------------------------------------------------------------
@app.websocket("/ws/gate/monitor")
async def websocket_dashboard_monitor_root(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """
    WebSocket endpoint for authenticated frontend SOC clients to receive live telemetry.
    """
    await websocket_dashboard_monitor(websocket, token=token)


from fastapi.encoders import jsonable_encoder

# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------
@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder({"detail": exc.errors(), "message": "Validation error"}),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(
        "smartguard.app Unhandled exception on %s %s: %s",
        request.method, request.url.path, type(exc).__name__,
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal error occurred. Please contact the administrator."},
    )
