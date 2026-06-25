from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class GraphEntity(BaseModel):
    entity_id: str = Field(..., min_length=1, max_length=128)
    entity_type: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphRelationship(BaseModel):
    source_id: str = Field(..., min_length=1, max_length=128)
    target_id: str = Field(..., min_length=1, max_length=128)
    relationship_type: str = Field(..., min_length=1, max_length=64)
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphRelationshipResult(GraphRelationship):
    relationship_id: str


class GraphQueryRequest(BaseModel):
    cypher: str = Field(..., min_length=1, max_length=2000)
    parameters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=20, ge=1, le=100)


class GraphQueryResponse(BaseModel):
    query_type: Literal["cypher", "evidence"]
    rows: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class GraphSeedResponse(BaseModel):
    entities: int
    relationships: int
    evidence: list[str] = Field(default_factory=list)
