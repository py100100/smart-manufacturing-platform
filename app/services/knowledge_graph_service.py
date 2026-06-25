from __future__ import annotations

import re
from hashlib import sha1
from typing import Any

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.schemas.knowledge_graph import (
    GraphEntity,
    GraphRelationship,
    GraphRelationshipResult,
)
from app.services.neo4j_health_service import GraphDatabase

logger = get_logger(__name__)

_IDENTIFIER_RE = re.compile(r"[^0-9A-Za-z_\u4e00-\u9fff]+")
_READ_ONLY_PREFIXES = ("MATCH", "RETURN", "WITH", "CALL DB.", "CALL DBMS.", "SHOW")
_RESERVED_PROPERTY_KEYS = {"id", "entity_id", "name", "type", "entity_type"}


def _safe_identifier(value: str, fallback: str = "Entity") -> str:
    cleaned = _IDENTIFIER_RE.sub("_", value.strip()).strip("_")
    if not cleaned:
        return fallback
    if cleaned[0].isdigit():
        cleaned = f"{fallback}_{cleaned}"
    return cleaned[:64]


def _safe_properties(properties: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in properties.items() if k not in _RESERVED_PROPERTY_KEYS}


class KnowledgeGraphService:
    """Neo4j-backed manufacturing knowledge graph service."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def is_enabled(self) -> bool:
        return bool(self.settings.neo4j_enabled and GraphDatabase is not None)

    def _driver(self):
        if not self.is_enabled:
            return None
        return GraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_user, self.settings.neo4j_password),
            connection_timeout=3,
        )

    def initialize(self) -> bool:
        driver = self._driver()
        if driver is None:
            return False
        try:
            with driver.session() as session:
                session.run(
                    "CREATE CONSTRAINT graph_entity_id IF NOT EXISTS "
                    "FOR (n:GraphEntity) REQUIRE n.id IS UNIQUE"
                ).consume()
            return True
        except Exception as exc:
            logger.warning("knowledge graph initialize failed: %s", exc.__class__.__name__)
            return False
        finally:
            driver.close()

    def upsert_entity(self, entity: GraphEntity) -> GraphEntity | None:
        label = _safe_identifier(entity.entity_type)
        properties = _safe_properties(entity.properties)
        driver = self._driver()
        if driver is None:
            return None
        try:
            with driver.session() as session:
                record = session.run(
                    f"""
                    MERGE (n:GraphEntity:`{label}` {{id: $entity_id}})
                    SET n.name = $name,
                        n.type = $entity_type,
                        n.updated_at = datetime(),
                        n += $properties
                    RETURN n.id AS entity_id, n.type AS entity_type,
                           n.name AS name, properties(n) AS properties
                    """,
                    entity_id=entity.entity_id,
                    entity_type=entity.entity_type,
                    name=entity.name,
                    properties=properties,
                ).single()
            if not record:
                return None
            raw = dict(record["properties"])
            return GraphEntity(
                entity_id=record["entity_id"],
                entity_type=record["entity_type"],
                name=record["name"],
                properties={k: v for k, v in raw.items() if k not in {"id", "name", "type"}},
            )
        except Exception as exc:
            logger.warning("knowledge graph entity upsert failed: %s", exc.__class__.__name__)
            return None
        finally:
            driver.close()

    def upsert_relationship(
        self, relationship: GraphRelationship
    ) -> GraphRelationshipResult | None:
        rel_type = _safe_identifier(relationship.relationship_type, "REL")
        rel_id = self._relationship_id(relationship)
        properties = _safe_properties(relationship.properties)
        driver = self._driver()
        if driver is None:
            return None
        try:
            with driver.session() as session:
                record = session.run(
                    f"""
                    MATCH (source:GraphEntity {{id: $source_id}})
                    MATCH (target:GraphEntity {{id: $target_id}})
                    MERGE (source)-[r:`{rel_type}` {{id: $relationship_id}}]->(target)
                    SET r.type = $relationship_type,
                        r.updated_at = datetime(),
                        r += $properties
                    RETURN r.id AS relationship_id,
                           source.id AS source_id,
                           target.id AS target_id,
                           r.type AS relationship_type,
                           properties(r) AS properties
                    """,
                    source_id=relationship.source_id,
                    target_id=relationship.target_id,
                    relationship_id=rel_id,
                    relationship_type=relationship.relationship_type,
                    properties=properties,
                ).single()
            if not record:
                return None
            raw = dict(record["properties"])
            return GraphRelationshipResult(
                relationship_id=record["relationship_id"],
                source_id=record["source_id"],
                target_id=record["target_id"],
                relationship_type=record["relationship_type"],
                properties={k: v for k, v in raw.items() if k not in {"id", "type"}},
            )
        except Exception as exc:
            logger.warning("knowledge graph relationship upsert failed: %s", exc.__class__.__name__)
            return None
        finally:
            driver.close()

    def run_read_query(
        self,
        cypher: str,
        parameters: dict[str, Any] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if not self._is_read_only(cypher):
            raise ValueError("Only read-only Cypher queries are allowed.")

        driver = self._driver()
        if driver is None:
            return []
        rows: list[dict[str, Any]] = []
        try:
            with driver.session() as session:
                result = session.run(cypher, **(parameters or {}))
                for index, record in enumerate(result):
                    if index >= limit:
                        break
                    rows.append(record.data())
            return rows
        except Exception as exc:
            logger.warning("knowledge graph query failed: %s", exc.__class__.__name__)
            return []
        finally:
            driver.close()

    def search_evidence(self, query: str, limit: int = 5) -> list[str]:
        terms = self._terms(query)
        if not terms:
            return []

        rows = self.run_read_query(
            """
            MATCH (n:GraphEntity)
            WHERE any(term IN $terms WHERE
                toLower(coalesce(n.name, "")) CONTAINS term OR
                toLower(coalesce(n.id, "")) CONTAINS term OR
                toLower(coalesce(n.type, "")) CONTAINS term
            )
            OPTIONAL MATCH (n)-[r]-(m:GraphEntity)
            RETURN n.id AS id,
                   n.name AS name,
                   n.type AS type,
                   collect(DISTINCT {
                       relationship: type(r),
                       neighbor_id: m.id,
                       neighbor_name: m.name,
                       neighbor_type: m.type
                   }) AS relations
            LIMIT $limit
            """,
            {"terms": terms, "limit": limit},
            limit=limit,
        )
        evidence: list[str] = []
        for row in rows:
            relations = [
                r for r in (row.get("relations") or [])
                if r.get("relationship") and r.get("neighbor_name")
            ]
            if relations:
                rel = relations[0]
                evidence.append(
                    "[graph:Neo4j] "
                    f"{row.get('name')}({row.get('type')}) "
                    f"-[{rel.get('relationship')}]- "
                    f"{rel.get('neighbor_name')}({rel.get('neighbor_type')})"
                )
            else:
                evidence.append(
                    "[graph:Neo4j] "
                    f"{row.get('name')}({row.get('type')}) matched graph entity"
                )
        return evidence

    def seed_demo_graph(self) -> tuple[int, int, list[str]]:
        entities = [
            GraphEntity(entity_id="equipment:CNC-001", entity_type="Equipment", name="CNC-001"),
            GraphEntity(entity_id="process:CNC-machining", entity_type="Process", name="CNC 加工"),
            GraphEntity(entity_id="defect:dimension-deviation", entity_type="Defect", name="尺寸偏差"),
            GraphEntity(entity_id="sensor:vibration", entity_type="Sensor", name="振动传感器"),
            GraphEntity(entity_id="parameter:temperature", entity_type="Parameter", name="热处理温度"),
            GraphEntity(entity_id="material:steel", entity_type="Material", name="钢材"),
        ]
        relationships = [
            GraphRelationship(source_id="equipment:CNC-001", target_id="process:CNC-machining", relationship_type="SUPPORTS"),
            GraphRelationship(source_id="process:CNC-machining", target_id="defect:dimension-deviation", relationship_type="MAY_CAUSE"),
            GraphRelationship(source_id="sensor:vibration", target_id="equipment:CNC-001", relationship_type="MONITORS"),
            GraphRelationship(source_id="parameter:temperature", target_id="defect:dimension-deviation", relationship_type="AFFECTS"),
            GraphRelationship(source_id="material:steel", target_id="process:CNC-machining", relationship_type="CONSUMED_BY"),
        ]

        entity_count = 0
        relationship_count = 0
        self.initialize()
        for entity in entities:
            if self.upsert_entity(entity):
                entity_count += 1
        for relationship in relationships:
            if self.upsert_relationship(relationship):
                relationship_count += 1
        evidence = self.search_evidence("CNC 振动 尺寸偏差 钢材", limit=5)
        return entity_count, relationship_count, evidence

    @staticmethod
    def _relationship_id(relationship: GraphRelationship) -> str:
        raw = "|".join([
            relationship.source_id,
            relationship.relationship_type,
            relationship.target_id,
        ])
        return f"rel:{sha1(raw.encode('utf-8')).hexdigest()[:16]}"

    @staticmethod
    def _is_read_only(cypher: str) -> bool:
        stripped = cypher.strip()
        upper = stripped.upper()
        if not any(upper.startswith(prefix) for prefix in _READ_ONLY_PREFIXES):
            return False
        forbidden = ("CREATE ", "MERGE ", "DELETE ", "DETACH ", "SET ", "REMOVE ", "DROP ", "LOAD CSV")
        return not any(token in upper for token in forbidden)

    @staticmethod
    def _terms(query: str) -> list[str]:
        raw_terms = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_-]{2,}", query.lower())
        seen: set[str] = set()
        terms: list[str] = []
        for term in raw_terms:
            if term not in seen:
                seen.add(term)
                terms.append(term)
        return terms[:12]
