"""FastAPI application entry point.

Swagger UI is at /docs, ReDoc at /redoc, raw schema at /openapi.json.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.config import settings
from app.database import check_connection, engine, init_db
from app.routers import data, demand, optimization, products, stores

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
)
logger = logging.getLogger("darkstore")


DESCRIPTION = """
Joint **dark-store location** and **inventory allocation** optimization for
quick commerce, solved two ways on the same instance and compared.

### Solvers
* **QAOA** - Qiskit `QAOAAnsatz` + `StatevectorSampler` on a local simulator.
  A sampling heuristic. It does **not** enumerate the search space and carries
  **no optimality guarantee**. Quality depends on circuit depth (`reps`),
  `shots` and `maxiter`; low depth can return a feasible but suboptimal plan.
* **Classical** - PuLP + CBC branch and bound. When CBC reports `Optimal`, the
  result is a **proven** optimum for this instance.

### Honest reporting
* Both solutions are checked by an **independent validator** that re-derives
  every constraint from the raw data and reads neither the QUBO nor the
  solver's own verdict.
* An **optimality gap** is published only when a proven reference exists.
* The word *accuracy* is not used: these are objective values, not predictions.

### Data provenance
Store areas and counts for Puducherry come from the project owner. Coordinates
are **approximate area centroids** and all operating costs, capacities and
demand are **clearly labelled demo assumptions** (`data_source` column), not
observed operator data.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail loudly rather than silently serving an empty local database.
    settings.assert_database_allowed()
    ok, message = check_connection()
    if ok:
        logger.info("database: %s", message)
        init_db()
        logger.info("database tables ensured")
    else:
        # Start anyway so /health can report the problem and /docs still loads.
        logger.error("database unavailable: %s", message)
    yield
    engine.dispose()
    logger.info("shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Explicit origin list, not "*". The Vite dev server origins are configurable
# through CORS_ORIGINS in backend/.env.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stores.router)
app.include_router(products.router)
app.include_router(demand.router)
app.include_router(optimization.router)
app.include_router(data.router)


# ===========================================================================
# Error handling -- never return a fake success, always say what went wrong
# ===========================================================================
@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """422 with the offending field path, so a bad value is easy to find."""
    problems = [
        {
            "field": ".".join(str(p) for p in err.get("loc", [])),
            "message": err.get("msg"),
            "type": err.get("type"),
        }
        for err in exc.errors()
    ]
    logger.warning("validation failed on %s: %s", request.url.path, problems)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "error": "request validation failed",
            "path": request.url.path,
            "problems": problems,
            "hint": "demand, inventory, costs and budget must be non-negative; "
            "unit_volume must be greater than zero; store and product ids must exist",
        },
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(
    request: Request, exc: IntegrityError
) -> JSONResponse:
    """A database CHECK or UNIQUE constraint rejected the write."""
    logger.warning("integrity error on %s: %s", request.url.path, exc.orig)
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "error": "database constraint violated",
            "path": request.url.path,
            "detail": str(getattr(exc, "orig", exc)),
        },
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    logger.exception("database error on %s", request.url.path)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": "database error",
            "path": request.url.path,
            "detail": f"{type(exc).__name__}: {exc}",
            "hint": "check DATABASE_URL and that the server is reachable; "
            "GET /health reports connectivity",
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Anything unexpected. The type and message are returned on purpose:
    this is a research backend and a silent 500 wastes debugging time."""
    logger.exception("unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "unhandled server error",
            "path": request.url.path,
            "detail": f"{type(exc).__name__}: {exc}",
        },
    )


# ===========================================================================
# Meta endpoints
# ===========================================================================
@app.get("/", tags=["meta"], summary="Service metadata")
def root() -> dict:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "stores": "/api/stores",
            "products": "/api/products",
            "demand": "/api/demand",
            "optimization": "/api/optimization/run",
            "data_sources": "/api/data/sources",
            "data_status": "/api/data/status",
        },
    }


def _database_host() -> str:
    """Host portion of DATABASE_URL. Never returns user, password or query."""
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(settings.database_url.split("://", 1)[-1])
        raw = settings.database_url.split("@")[-1] if "@" in settings.database_url else ""
        return raw.split("/")[0] or (parts.path.split("/")[0] if parts.path else "local")
    except Exception:  # pragma: no cover - defensive
        return "unknown"


@app.get("/health", tags=["meta"], summary="Liveness and database check")
def health() -> JSONResponse:
    ok, message = check_connection()
    body = {
        "status": "ok" if ok else "degraded",
        "database": message,
        "dialect": engine.dialect.name,
        "driver": engine.dialect.driver,
        # Never includes credentials: host only, parsed from the URL.
        "database_host": _database_host(),
        "sqlite_fallback_allowed": settings.allow_sqlite,
        "cors_origins": settings.cors_origin_list,
        "qaoa_max_qubits": settings.qaoa_max_qubits,
    }
    return JSONResponse(
        status_code=status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=body,
    )
