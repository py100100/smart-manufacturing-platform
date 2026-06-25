from __future__ import annotations

from typing import Any

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

try:
    from neo4j import GraphDatabase
except ImportError:  # pragma: no cover - optional dependency fallback
    GraphDatabase = None

logger = get_logger(__name__)


class Neo4jHealthService:
    """Lightweight Neo4j connectivity probe for the knowledge graph layer."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def is_enabled(self) -> bool:
        return bool(self.settings.neo4j_enabled)

    def check_ready(self) -> bool:
        if not self.is_enabled:
            return False
        if GraphDatabase is None:
            logger.warning("neo4j health check skipped: driver unavailable")
            return False

        driver: Any = None
        try:
            driver = GraphDatabase.driver(
                self.settings.neo4j_uri,
                auth=(self.settings.neo4j_user, self.settings.neo4j_password),
                connection_timeout=3,
            )
            with driver.session() as session:
                record = session.run("RETURN 1 AS ok").single()
            return bool(record and record.get("ok") == 1)
        except Exception as exc:
            logger.warning("neo4j health check failed: %s", exc.__class__.__name__)
            return False
        finally:
            if driver is not None:
                driver.close()
