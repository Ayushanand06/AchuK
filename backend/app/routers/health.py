# health.py — liveness + model status endpoints.

from fastapi import APIRouter

from app.settings import settings
from app.schemas.responses import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", mappls_configured=settings.mappls_configured)


@router.get("/api/health/models", response_model=HealthResponse)
def health_models():
    """Eagerly load all models and report each model's class labels."""
    from app.services.inference import warmup
    return HealthResponse(
        status="ok",
        mappls_configured=settings.mappls_configured,
        models=warmup(),
    )
