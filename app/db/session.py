from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import Base
from app.models import agent_run  # noqa: F401

logger = get_logger(__name__)
settings = get_settings()

engine = create_engine(
    settings.mysql_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.debug,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def ensure_database_exists() -> None:
    bootstrap_url = (
        f"mysql+pymysql://{settings.mysql_user}:{settings.mysql_password}"
        f"@{settings.mysql_host}:{settings.mysql_port}/mysql?charset=utf8mb4"
    )
    bootstrap_engine = create_engine(bootstrap_url, pool_pre_ping=True, echo=False)
    with bootstrap_engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{settings.mysql_db}` "
                "DEFAULT CHARACTER SET utf8mb4"
            )
        )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def initialize_database() -> bool:
    try:
        ensure_database_exists()
        with engine.begin() as connection:
            connection.execute(text("SELECT 1"))
        Base.metadata.create_all(bind=engine)
        return True
    except SQLAlchemyError as exc:
        logger.warning("database initialization skipped: %s", exc)
        return False
