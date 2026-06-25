from fastapi import APIRouter

from app.api.v1.endpoints import agents, demo, governance, health, knowledge_graph

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(agents.router)
api_router.include_router(demo.router)
api_router.include_router(knowledge_graph.router)
api_router.include_router(governance.router)
