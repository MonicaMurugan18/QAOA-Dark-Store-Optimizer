"""SQLAlchemy engine, session factory and declarative base."""

from __future__ import annotations

import re
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# Seconds to wait for the TCP connect + auth handshake before giving up.
# Without this libpq waits on the OS default, so an unreachable host hangs a
# request for over a minute instead of failing with something actionable.
CONNECT_TIMEOUT_SEC = 15


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""


def _scrub(msg: str) -> str:
    """Strip any user:password pair that a driver echoed into its error."""
    return re.sub(r"(://[^:/@\s]+:)[^@\s]*(@)", r"\1****\2", str(msg))


def safe_host() -> str:
    """host:port from DATABASE_URL, never the credentials."""
    try:
        return f"{settings.database_url.split('@')[-1].split('/')[0]}"
    except Exception:  # pragma: no cover - defensive only
        return "(unparsed)"


def _engine_kwargs() -> dict:
    kwargs: dict = {"echo": settings.sql_echo, "future": True}
    if settings.is_sqlite:
        # SQLite only: allow the connection to be shared across FastAPI's
        # threadpool workers. Not needed (or valid) for PostgreSQL.
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # pool_pre_ping matters against a pooler: Supabase may close an idle
        # server-side connection, and without the ping the next request would
        # fail on a dead socket instead of transparently reconnecting.
        kwargs["pool_pre_ping"] = True
        kwargs["pool_recycle"] = 1800
        kwargs["connect_args"] = {"connect_timeout": CONNECT_TIMEOUT_SEC}
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
        detail = _scrub(exc)
        # A name-resolution failure is the one case worth naming explicitly:
        # it is a DNS/network problem, not a credential or SQL problem, and
        # saying so saves the reader from chasing the password.
        if "getaddrinfo" in detail or "could not translate host name" in detail:
            detail += (
                f" -- DNS could not resolve {safe_host()}. Supabase DIRECT "
                "database hosts (db.<ref>.supabase.co) are IPv6-only; if this "
                "network has no IPv6, use the session pooler host from the "
                "Supabase dashboard instead."
            )
        return False, f"{type(exc).__name__}: {detail}"
