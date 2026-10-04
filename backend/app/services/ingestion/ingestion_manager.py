"""Orchestrates the ingestion pipeline and records provenance.

Order matters: zones and stores must exist before routing can be computed, and
zones and products must exist before the demand proxy can run.

    stores ──┐
             ├──> travel_times
    zones  ──┘
             └──> demand (needs products too)
    products ─┘
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    DataIngestionRun,
    DataSource,
    Demand,
    DemandZone,
    Product,
    Store,
    TravelTime,
)
from app.services.ingestion import (
    demand_ingestion,
    osm_ingestion,
    product_ingestion,
    store_ingestion,
    zone_ingestion,
)
from app.services.ingestion.base import IngestionError, IngestionReport

logger = logging.getLogger("darkstore.ingestion")

#: Every dataset the pipeline knows about, in dependency order.
STEPS = ["stores", "zones", "products", "travel_times", "demand"]

SOURCE_METADATA = [
    store_ingestion.SOURCE_META,
    zone_ingestion.SOURCE_META,
    zone_ingestion.POPULATION_SOURCE_META,
    product_ingestion.SOURCE_META,
    osm_ingestion.SOURCE_META,
    demand_ingestion.SOURCE_META,
    # Costs and capacity have no external source. They are registered anyway so
    # the provenance API can state plainly that they are assumptions.
    {
        "key": "prototype_assumptions",
        "dataset": "Store economics (cost, capacity) and handling time",
        "source_type": "synthetic",
        "source_name": "Prototype assumptions",
        "source_url": None,
        "licence": None,
        "feeds": "stores.opening_cost, stores.storage_capacity, handling time",
        "notes": (
            "Opening cost, storage capacity, rider cost and picking time are "
            "NOT observed. They require operator data obtained with "
            "authorisation. Values are carried from the prototype and every "
            "affected column is marked synthetic so they are never confused "
            "with the real location and routing data."
        ),
    },
]


def register_sources(db: Session) -> None:
    """Upsert the source catalogue. Safe to call on every startup."""
    for meta in SOURCE_METADATA:
        row = db.execute(
            select(DataSource).where(DataSource.key == meta["key"])
        ).scalar_one_or_none()
        if row is None:
            row = DataSource(key=meta["key"])
            db.add(row)
        for field in (
            "dataset",
            "source_type",
            "source_name",
            "source_url",
            "licence",
            "feeds",
            "notes",
        ):
            setattr(row, field, meta.get(field))
    db.commit()


#: Which table each registered source feeds, for live record counts.
_COUNT_FOR = {
    "osm_stores": lambda db: db.execute(
        select(func.count()).select_from(Store)
    ).scalar_one(),
    "osm_zones": lambda db: db.execute(
        select(func.count()).select_from(DemandZone)
    ).scalar_one(),
    "census_population": lambda db: db.execute(
        select(func.count()).select_from(DemandZone).where(
            DemandZone.population.isnot(None)
        )
    ).scalar_one(),
    "blinkit_catalogue": lambda db: db.execute(
        select(func.count()).select_from(Product)
    ).scalar_one(),
    "osrm_routing": lambda db: db.execute(
        select(func.count()).select_from(TravelTime)
    ).scalar_one(),
    "demand_proxy": lambda db: db.execute(
        select(func.count()).select_from(Demand)
    ).scalar_one(),
    "prototype_assumptions": lambda db: db.execute(
        select(func.count()).select_from(Store)
    ).scalar_one(),
}


def refresh_source_counts(db: Session) -> None:
    """Update record_count and status from what is actually in the database."""
    for row in db.execute(select(DataSource)).scalars():
        counter = _COUNT_FOR.get(row.key)
        if counter is None:
            continue
        try:
            count = int(counter(db))
        except Exception:  # pragma: no cover - defensive
            continue
        row.record_count = count
        row.status = "loaded" if count else "not_loaded"
    db.commit()


def run_ingestion(
    db: Session,
    *,
    steps: list[str] | None = None,
    use_cache: bool = True,
    use_router: bool = True,
    zone_limit: int | None = None,
    product_limit: int | None = None,
) -> DataIngestionRun:
    """Execute the pipeline and persist a full report.

    A failing step is recorded and the remaining steps still run, so one dead
    endpoint does not block the whole refresh.
    """
    wanted = steps or STEPS
    unknown = [s for s in wanted if s not in STEPS]
    if unknown:
        raise ValueError(f"unknown ingestion step(s): {unknown}; valid: {STEPS}")

    register_sources(db)

    run = DataIngestionRun(requested=wanted, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)

    report: dict[str, dict] = {}
    failures: list[str] = []

    for step in STEPS:
        if step not in wanted:
            continue
        logger.info("ingestion step: %s", step)
        try:
            if step == "stores":
                r = store_ingestion.ingest_stores(db, use_cache=use_cache)
            elif step == "zones":
                r = zone_ingestion.ingest_zones(db, use_cache=use_cache)
            elif step == "products":
                r = product_ingestion.ingest_products(db)
            elif step == "travel_times":
                r = osm_ingestion.ingest_travel_times(
                    db, use_router=use_router, max_zones=zone_limit
                )
            else:
                r = demand_ingestion.ingest_demand(
                    db, zone_limit=zone_limit, product_limit=product_limit
                )
            report[step] = r.to_dict()
        except (IngestionError, Exception) as exc:  # noqa: BLE001 - surfaced below
            logger.exception("ingestion step %s failed", step)
            failures.append(f"{step}: {type(exc).__name__}: {exc}")
            report[step] = IngestionReport(
                dataset=step, skipped_reason=f"{type(exc).__name__}: {exc}"
            ).to_dict()

    refresh_source_counts(db)
    now = datetime.now(timezone.utc)
    for src in db.execute(select(DataSource)).scalars():
        if src.status == "loaded":
            src.ingested_at = now

    run.finished_at = now
    run.report = report
    run.status = "completed_with_errors" if failures else "completed"
    run.error_message = "; ".join(failures)[:4000] if failures else None
    db.commit()
    db.refresh(run)
    return run


def data_status(db: Session) -> dict:
    """A plain summary of what is real and what is assumed."""
    sources = [s.to_dict() for s in db.execute(select(DataSource)).scalars()]

    real = [s for s in sources if s["is_real"]]
    proxy = [s for s in sources if s["source_type"] in {"proxy", "estimated"}]
    synthetic = [s for s in sources if s["source_type"] == "synthetic"]

    routed = db.execute(
        select(func.count()).select_from(TravelTime).where(TravelTime.source == "osrm")
    ).scalar_one()
    fallback = db.execute(
        select(func.count())
        .select_from(TravelTime)
        .where(TravelTime.source == "haversine_fallback")
    ).scalar_one()
    zones_with_pop = db.execute(
        select(func.count()).select_from(DemandZone).where(
            DemandZone.population.isnot(None)
        )
    ).scalar_one()
    zones_total = db.execute(
        select(func.count()).select_from(DemandZone)
    ).scalar_one()

    last = db.execute(
        select(DataIngestionRun).order_by(DataIngestionRun.id.desc()).limit(1)
    ).scalar_one_or_none()

    return {
        "database_dialect": db.bind.dialect.name if db.bind else None,
        "demand_mode": demand_ingestion.DEMAND_MODE,
        "counts": {
            "stores": db.execute(select(func.count()).select_from(Store)).scalar_one(),
            "demand_zones": zones_total,
            "products": db.execute(
                select(func.count()).select_from(Product)
            ).scalar_one(),
            "demand_rows": db.execute(
                select(func.count()).select_from(Demand)
            ).scalar_one(),
            "travel_times": routed + fallback,
        },
        "real_data": [s["dataset"] for s in real],
        "proxy_or_estimated": [s["dataset"] for s in proxy],
        "synthetic": [s["dataset"] for s in synthetic],
        "routing": {
            "routed_by_osrm": routed,
            "haversine_fallback": fallback,
            "all_real_routes": fallback == 0 and routed > 0,
        },
        "population_coverage": {
            "zones_with_sourced_population": zones_with_pop,
            "zones_total": zones_total,
            "note": (
                "Zones without a sourced figure receive an allocated share of "
                "commune population. That allocation is an estimate, not a "
                "ward-level observation."
            ),
        },
        "last_ingestion": last.to_dict() if last else None,
        "caveats": [
            "Demand is a population-derived PROXY, not observed customer orders.",
            "Store opening cost and storage capacity are prototype assumptions.",
            "Rider cost and picking time are assumptions.",
            "Candidate stores are OSM-mapped retail outlets, not verified "
            "operating dark stores.",
        ],
    }
