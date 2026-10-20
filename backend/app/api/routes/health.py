"""
SmartGuard AI — Health Check Routes
GET /api/health/live   — liveness probe
GET /api/health/ready  — readiness probe (checks DB + pgvector)
"""
import logging
from fastapi import APIRouter, Response, status

from app.db.session import check_database_readiness
from app.schemas.account import LivenessResponse, ReadinessResponse
from app.core.config import get_settings

router = APIRouter(prefix="/health", tags=["Health"])
logger = logging.getLogger("smartguard.health")


@router.get("/live", response_model=LivenessResponse, summary="Liveness probe")
def liveness() -> LivenessResponse:
    """Return 200 when the process is running."""
    return LivenessResponse(status="ok")


@router.get("/ready", summary="Readiness probe")
def readiness(response: Response) -> ReadinessResponse:
    """
    Check actual infrastructure availability.
    Returns 200 only when both database and pgvector are available.
    """
    settings = get_settings()
    db_ok, pgvector_ok = check_database_readiness()

    all_ready = db_ok and pgvector_ok
    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        logger.warning(
            "smartguard.health Readiness check FAILED db=%s pgvector=%s", db_ok, pgvector_ok
        )
    else:
        logger.info(
            "smartguard.health Readiness check OK db=%s pgvector=%s", db_ok, pgvector_ok
        )

    return ReadinessResponse(
        status="ready" if all_ready else "unavailable",
        database=db_ok,
        pgvector=pgvector_ok,
        environment=settings.app_env if settings.is_development else None,
    )
