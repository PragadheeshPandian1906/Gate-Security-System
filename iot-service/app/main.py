"""
SmartGuard AI — IoT Microservice FastAPI Application
Independently runnable Python service managing:
  - ESP32 gate controller WebSocket connection
  - Automated gate decision processing
  - Manual operator gate commands
  - Real-time monitoring dashboard
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.api.routes import router
from app.services.device_manager import device_manager

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
)
logger = logging.getLogger("iot.app")
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("SmartGuard IoT Microservice starting on port %s", settings.iot_service_port)
    try:
        settings.validate_critical()
        logger.info("Configuration validated")
    except ValueError as exc:
        logger.warning("Configuration warning: %s (service will start but may be insecure)", exc)

    # Capture running event loop for thread-safe dispatches from sync callers
    device_manager.set_loop(asyncio.get_running_loop())

    yield

    logger.info("SmartGuard IoT Microservice shutting down")


# ─────────────────────────────────────────────────────────────────────────────
# Application
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SmartGuard IoT Microservice",
    version="1.0.0",
    description="Physical ESP32 gate controller management and monitoring",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow frontend and main backend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Service-Secret", "X-Operator-Role", "X-Operator-Id"],
)

# ─────────────────────────────────────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────────────────────────────────────
app.include_router(router, prefix="/api/v1")

# ─────────────────────────────────────────────────────────────────────────────
# Serve monitoring dashboard HTML
# ─────────────────────────────────────────────────────────────────────────────
DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"


@app.get("/", include_in_schema=False)
@app.get("/monitor", include_in_schema=False)
async def serve_dashboard():
    index_path = DASHBOARD_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "IoT Monitoring Dashboard not found — place dashboard/index.html"}
