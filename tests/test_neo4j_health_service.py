from __future__ import annotations

from types import SimpleNamespace

from app.services import neo4j_health_service
from app.services.neo4j_health_service import Neo4jHealthService


def make_settings(**overrides):
    data = {
        "neo4j_enabled": True,
        "neo4j_uri": "bolt://127.0.0.1:7687",
        "neo4j_user": "neo4j",
        "neo4j_password": "password",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_disabled_graph_health_is_not_ready() -> None:
    service = Neo4jHealthService(make_settings(neo4j_enabled=False))

    assert service.check_ready() is False


def test_graph_health_uses_lightweight_probe(monkeypatch) -> None:
    class FakeRecord:
        def get(self, key: str):
            return 1 if key == "ok" else None

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def run(self, query: str):
            assert query == "RETURN 1 AS ok"
            return self

        def single(self):
            return FakeRecord()

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

    monkeypatch.setattr(neo4j_health_service, "GraphDatabase", FakeGraphDatabase)

    service = Neo4jHealthService(make_settings())

    assert service.check_ready() is True
