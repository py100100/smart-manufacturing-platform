from fastapi import APIRouter

from app.api.v1.endpoints import agents, governance, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(agents.router)
api_router.include_router(governance.router)
