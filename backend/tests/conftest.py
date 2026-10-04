"""Shared test fixtures.

The suite runs against a throwaway SQLite file, not PostgreSQL. That keeps the
tests independent of any database credentials while exercising exactly the same
SQLAlchemy models, routers and services. PostgreSQL is validated separately by
pointing DATABASE_URL at a real server (see README).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# Must be set BEFORE app.config is imported, because Settings reads the
# environment once and get_settings() is cached.
_TMP_DIR = tempfile.mkdtemp(prefix="darkstore_tests_")
_DB_PATH = Path(_TMP_DIR) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH.as_posix()}"
os.environ["DEBUG"] = "false"
# The app refuses SQLite unless explicitly opted into; the test
# suite is exactly that case, so it says so out loud.
os.environ["ALLOW_SQLITE"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.data_service import (  # noqa: E402
    build_instance,
    dev_instance_ids,
    seed_database,
)


@pytest.fixture(scope="session", autouse=True)
def _prepare_database():
    init_db()
    db = SessionLocal()
    try:
        seed_database(db, reset=True)
    finally:
        db.close()
    yield
    engine.dispose()


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def dev_ids(db):
    """The small 3 stores x 3 areas x 3 products development instance."""
    return dev_instance_ids(db)


@pytest.fixture
def instance(db, dev_ids):
    return build_instance(db, budget=20000, **dev_ids)


# The verified optimum for the seeded dev instance. Used only to assert that
# independent routes AGREE with each other -- never injected into a solver.
KNOWN_OPTIMUM = 14716.14
