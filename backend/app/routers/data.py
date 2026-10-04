"""Data provenance endpoints.

The point of these is that a viewer can tell, without reading any code, which
numbers in this system are observed and which are assumptions.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SOURCE_TYPE_DESCRIPTION, DataIngestionRun, DataSource
from app.services.ingestion.ingestion_manager import (
    STEPS,
    data_status,
    refresh_source_counts,
    register_sources,
    run_ingestion,
)

router = APIRouter(prefix="/api/data", tags=["data provenance"])


@router.get(
    "/sources",
    summary="Every dataset, with its source, type, date and record count",
    description=(
        "Lists each registered dataset and whether it is real public data, "
        "official government data, a proxy, an estimate, or a prototype "
        "assumption. Grouped so real data is never shown alongside synthetic "
        "data without a label."
    ),
)
def list_sources(db: Session = Depends(get_db)) -> dict:
    register_sources(db)
    refresh_source_counts(db)
    rows = [s.to_dict() for s in db.execute(select(DataSource).order_by(DataSource.id)).scalars()]

    groups = {"real": [], "proxy_estimated": [], "synthetic": []}
    for r in rows:
        if r["is_real"]:
            groups["real"].append(r)
        elif r["source_type"] == "synthetic":
            groups["synthetic"].append(r)
        else:
            groups["proxy_estimated"].append(r)

    return {
        "sources": rows,
        "grouped": groups,
        "source_type_glossary": SOURCE_TYPE_DESCRIPTION,
        "disclaimer": (
            "Datasets marked proxy, estimated or synthetic are NOT observations. "
            "Demand is derived from population, not from customer orders. Store "
            "opening cost and storage capacity are prototype assumptions."
        ),
    }


@router.get(
    "/status",
    summary="What is loaded, what is real, and what is still assumed",
)
def get_status(db: Session = Depends(get_db)) -> dict:
    register_sources(db)
    refresh_source_counts(db)
    return data_status(db)


@router.get("/ingestion-runs", summary="History of ingestion runs")
def list_runs(
    db: Session = Depends(get_db), limit: int = Query(default=20, ge=1, le=200)
) -> list[dict]:
    rows = db.execute(
        select(DataIngestionRun).order_by(DataIngestionRun.id.desc()).limit(limit)
    ).scalars()
    return [r.to_dict() for r in rows]


@router.post(
    "/refresh",
    summary="Re-run the ingestion pipeline (explicit, manual operation)",
    description=(
        "Downloads are NEVER performed on server startup. This endpoint is the "
        "only automatic path, and it is deliberately manual because the sources "
        "are free community endpoints (Overpass, OSRM, Wikidata). Use "
        "`steps` to refresh one dataset, and `fresh=false` to reuse the cached "
        "raw downloads in data/raw/."
    ),
)
def refresh(
    db: Session = Depends(get_db),
    steps: str | None = Query(
        default=None, description=f"comma-separated subset of {STEPS}"
    ),
    fresh: bool = Query(
        default=False, description="bypass the data/raw cache and re-download"
    ),
    use_router: bool = Query(
        default=True, description="use OSRM; if false, labelled estimates are written"
    ),
    zone_limit: int | None = Query(default=None, ge=1),
    product_limit: int | None = Query(default=None, ge=1),
) -> dict:
    wanted = [s.strip() for s in steps.split(",")] if steps else None
    try:
        run = run_ingestion(
            db,
            steps=wanted,
            use_cache=not fresh,
            use_router=use_router,
            zone_limit=zone_limit,
            product_limit=product_limit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return run.to_dict()
