from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.knowledge_graph import GraphEntity, GraphRelationship
from app.services import knowledge_graph_service
from app.services.knowledge_graph_service import KnowledgeGraphService


def make_settings(**overrides):
    data = {
        "neo4j_enabled": True,
        "neo4j_uri": "bolt://127.0.0.1:7687",
        "neo4j_user": "neo4j",
        "neo4j_password": "password",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


class FakeRecord(dict):
    def data(self):
        return dict(self)


class FakeResult:
    def __init__(self, records=None, single_record=None):
        self.records = records or []
        self.single_record = single_record

    def __iter__(self):
        return iter(self.records)

    def single(self):
        return self.single_record

    def consume(self):
        return None


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def run(self, cypher: str, **params):
        if "CREATE CONSTRAINT" in cypher:
            return FakeResult()
        if "MERGE (n:GraphEntity" in cypher:
            return FakeResult(single_record=FakeRecord({
                "entity_id": params["entity_id"],
                "entity_type": params["entity_type"],
                "name": params["name"],
                "properties": {
                    "id": params["entity_id"],
                    "type": params["entity_type"],
                    "name": params["name"],
                    **params.get("properties", {}),
                },
            }))
        if "MERGE (source)-[r:" in cypher:
            return FakeResult(single_record=FakeRecord({
                "relationship_id": params["relationship_id"],
                "source_id": params["source_id"],
                "target_id": params["target_id"],
                "relationship_type": params["relationship_type"],
                "properties": {
                    "id": params["relationship_id"],
                    "type": params["relationship_type"],
                    **params.get("properties", {}),
                },
            }))
        return FakeResult(records=[
            FakeRecord({
                "id": "equipment:CNC-001",
                "name": "CNC-001",
                "type": "Equipment",
                "relations": [{
                    "relationship": "MONITORS",
                    "neighbor_id": "sensor:vibration",
                    "neighbor_name": "振动传感器",
                    "neighbor_type": "Sensor",
                }],
            })
        ])


class FakeDriver:
    def session(self):
        return FakeSession()

    def close(self):
        return None


class FakeGraphDatabase:
    @staticmethod
    def driver(uri: str, auth: tuple[str, str], connection_timeout: int):
        assert uri == "bolt://127.0.0.1:7687"
        assert auth == ("neo4j", "password")
        assert connection_timeout == 3
        return FakeDriver()


def test_upsert_entity_and_relationship(monkeypatch) -> None:
    monkeypatch.setattr(knowledge_graph_service, "GraphDatabase", FakeGraphDatabase)
    service = KnowledgeGraphService(make_settings())

    entity = service.upsert_entity(GraphEntity(
        entity_id="equipment:CNC-001",
        entity_type="Equipment",
        name="CNC-001",
        properties={"line": "A"},
    ))
    relation = service.upsert_relationship(GraphRelationship(
        source_id="sensor:vibration",
        target_id="equipment:CNC-001",
        relationship_type="MONITORS",
        properties={"threshold": 10},
    ))

    assert entity is not None
    assert entity.entity_id == "equipment:CNC-001"
    assert relation is not None
    assert relation.relationship_type == "MONITORS"


def test_search_evidence_returns_graph_marker(monkeypatch) -> None:
    monkeypatch.setattr(knowledge_graph_service, "GraphDatabase", FakeGraphDatabase)
    service = KnowledgeGraphService(make_settings())

    evidence = service.search_evidence("CNC 振动", limit=3)

    assert evidence
    assert evidence[0].startswith("[graph:Neo4j]")
    assert "CNC-001" in evidence[0]


def test_read_query_rejects_writes(monkeypatch) -> None:
    monkeypatch.setattr(knowledge_graph_service, "GraphDatabase", FakeGraphDatabase)
    service = KnowledgeGraphService(make_settings())

    try:
        service.run_read_query("CREATE (n:Bad)")
    except ValueError as exc:
        assert "read-only" in str(exc)
    else:
        raise AssertionError("write query should be rejected")


def test_graph_api_rejects_write_cypher() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/graph/query",
        json={"cypher": "CREATE (n:Bad)", "parameters": {}, "limit": 5},
    )

    assert response.status_code == 400
