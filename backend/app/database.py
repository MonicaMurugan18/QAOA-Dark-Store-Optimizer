"""SQLAlchemy engine, session factory and declarative base."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""


def _engine_kwargs() -> dict:
    kwargs: dict = {"echo": settings.sql_echo, "future": True}
    if settings.is_sqlite:
        # SQLite only: allow the connection to be shared across FastAPI's
        # threadpool workers. Not needed (or valid) for PostgreSQL.
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_pre_ping"] = True
    return kwargs


engine = create_engine(settings.database_url, **_engine_kwargs())
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create any missing tables. Safe to call repeatedly."""
    from app import models  # noqa: F401  (registers the mappers)

    Base.metadata.create_all(bind=engine)


def check_connection() -> tuple[bool, str]:
    """Return (ok, message). Used by /health and by the connection test."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, f"connected to {engine.dialect.name}"
    except Exception as exc:  # pragma: no cover - depends on local setup
        return False, f"{type(exc).__name__}: {exc}"
