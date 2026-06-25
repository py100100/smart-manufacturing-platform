from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.knowledge_graph import (
    GraphEntity,
    GraphQueryRequest,
    GraphQueryResponse,
    GraphRelationship,
    GraphRelationshipResult,
    GraphSeedResponse,
)
from app.services.knowledge_graph_service import KnowledgeGraphService

router = APIRouter(prefix="/graph", tags=["knowledge-graph"])


@router.post("/entities", response_model=GraphEntity)
async def upsert_entity(entity: GraphEntity) -> GraphEntity:
    result = KnowledgeGraphService().upsert_entity(entity)
    if result is None:
        raise HTTPException(status_code=503, detail="Knowledge graph is unavailable")
    return result


@router.post("/relationships", response_model=GraphRelationshipResult)
async def upsert_relationship(
    relationship: GraphRelationship,
) -> GraphRelationshipResult:
    result = KnowledgeGraphService().upsert_relationship(relationship)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Relationship was not written; check source and target entities",
        )
    return result


@router.post("/query", response_model=GraphQueryResponse)
async def run_query(request: GraphQueryRequest) -> GraphQueryResponse:
    try:
        rows = KnowledgeGraphService().run_read_query(
            request.cypher,
            request.parameters,
            request.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GraphQueryResponse(query_type="cypher", rows=rows)


@router.get("/evidence", response_model=GraphQueryResponse)
async def read_graph_evidence(
    query: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(default=5, ge=1, le=20),
) -> GraphQueryResponse:
    evidence = KnowledgeGraphService().search_evidence(query, limit=limit)
    return GraphQueryResponse(query_type="evidence", evidence=evidence)


@router.post("/demo/seed", response_model=GraphSeedResponse)
async def seed_demo_graph() -> GraphSeedResponse:
    entity_count, relationship_count, evidence = KnowledgeGraphService().seed_demo_graph()
    if entity_count == 0:
        raise HTTPException(status_code=503, detail="Knowledge graph is unavailable")
    return GraphSeedResponse(
        entities=entity_count,
        relationships=relationship_count,
        evidence=evidence,
    )
