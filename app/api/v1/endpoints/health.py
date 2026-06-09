from fastapi import APIRouter

from app.core.config import get_settings
from app.db.session import initialize_database
from app.schemas.agent import HealthResponse
from app.services.deepseek_client import DeepSeekClient

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    database_ready = initialize_database()
    model_ready = DeepSeekClient().is_configured
    return HealthResponse(
        app_name=settings.app_name,
        version=settings.app_version,
        database_ready=database_ready,
        model_ready=model_ready,
    )
