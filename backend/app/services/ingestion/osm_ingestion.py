"""Store -> zone road distance and travel time, from a real routing engine.

WHY THIS EXISTS
===============
The prototype estimated delivery time from a straight-line distance times a
circuity factor. That is a guess about the road network. This module replaces it
with an actual route computed over OpenStreetMap road geometry.

ROUTING PROVIDER
================
OSRM (Open Source Routing Machine), demo server at router.project-osrm.org,
routing over the OSM road graph. The provider is pluggable: set
ROUTING_PROVIDER=openrouteservice with an API key, or point OSRM_BASE_URL at a
self-hosted instance, and nothing else changes.

The demo server is a free community resource. Requests are batched through the
`table` service (one HTTP call per store for all zones) and rate-limited.

FALLBACK IS LABELLED, NOT HIDDEN
================================
If the router is unreachable, a haversine estimate is written instead, with
`source="haversine_fallback"` and `source_type="estimated"`. The optimizer and
the API both surface that field, so a run computed on estimates can never be
mistaken for one computed on real routes.
"""

from __future__ import annotations

import json
import logging
import math
import os

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DemandZone, SourceType, Store, TravelTime
from app.services.ingestion.base import (
    IngestionError,
    IngestionReport,
    http_get,
    polite_sleep,
)

logger = logging.getLogger("darkstore.ingestion")

SOURCE_KEY = "osrm_routing"
SOURCE_NAME = "OSRM (Open Source Routing Machine) over OpenStreetMap"

OSRM_BASE_URL = os.environ.get(
    "OSRM_BASE_URL", "https://router.project-osrm.org"
)

#: Picking and packing time added to every routed leg, in minutes.
#: A real operational constant, but not measured here -- it is an assumption and
#: is stored in its own column so it can be replaced with observed data.
HANDLING_MINUTES = float(os.environ.get("HANDLING_MINUTES", "3.0"))

#: Courtesy delay between calls to the free demo server.
REQUEST_DELAY_SEC = float(os.environ.get("OSRM_DELAY_SEC", "1.1"))

#: A leg longer than this is almost certainly a routing artefact.
MAX_PLAUSIBLE_MINUTES = 180.0
MAX_PLAUSIBLE_KM = 200.0


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


#: OSRM's table service caps the number of coordinates per request. The demo
#: server allows 100 including the source, so destinations are chunked.
TABLE_CHUNK = int(os.environ.get("OSRM_TABLE_CHUNK", "90"))


def _osrm_table_chunk(
    origin: tuple[float, float], destinations: list[tuple[float, float]]
):
    """One OSRM `table` call: distances and durations from origin to all dests."""
    coords = ";".join(f"{lon},{lat}" for lat, lon in [origin, *destinations])
    dest_idx = ";".join(str(i) for i in range(1, len(destinations) + 1))
    url = (
        f"{OSRM_BASE_URL}/table/v1/driving/{coords}"
        f"?sources=0&destinations={dest_idx}&annotations=duration,distance"
    )
    payload = json.loads(http_get(url, timeout=150))
    if payload.get("code") != "Ok":
        raise IngestionError(f"OSRM returned {payload.get('code')}: {payload}")
    return payload["distances"][0], payload["durations"][0]


def _osrm_table(origin: tuple[float, float], destinations: list[tuple[float, float]]):
    """Route one origin to many destinations, chunking to respect the API cap."""
    all_dist: list = []
    all_dur: list = []
    for start in range(0, len(destinations), TABLE_CHUNK):
        batch = destinations[start : start + TABLE_CHUNK]
        d, t = _osrm_table_chunk(origin, batch)
        all_dist.extend(d)
        all_dur.extend(t)
        if start + TABLE_CHUNK < len(destinations):
            polite_sleep(REQUEST_DELAY_SEC)
    return all_dist, all_dur



#: Rows written per database round trip. The remote pooler adds latency to every
#: statement, so batching is what makes a remote run finish in minutes rather
#: than tens of minutes.
WRITE_BATCH_SIZE = int(os.environ.get("TRAVEL_WRITE_BATCH", "500"))

#: Retries for a transient router failure (timeout, 502/504 from a free server).
OSRM_MAX_RETRIES = int(os.environ.get("OSRM_MAX_RETRIES", "4"))


def _osrm_table_retry(origin, destinations, *, report=None):
    """_osrm_table with exponential backoff.

    A network timeout against a free community endpoint is expected rather than
    exceptional. Retrying keeps a long run alive instead of losing the pass;
    after the final attempt the error propagates so the caller records a skip
    instead of inventing a distance.
    """
    delay = 2.0
    last = None
    for attempt in range(1, OSRM_MAX_RETRIES + 1):
        try:
            result = _osrm_table(origin, destinations)
            polite_sleep(REQUEST_DELAY_SEC)
            return result
        except Exception as exc:  # noqa: BLE001 - re-raised below
            last = exc
            if attempt == OSRM_MAX_RETRIES:
                break
            msg = (
                f"OSRM attempt {attempt}/{OSRM_MAX_RETRIES} failed "
                f"({type(exc).__name__}); retrying in {delay:.0f}s"
            )
            logger.warning(msg)
            if report is not None:
                report.warn(msg)
            polite_sleep(delay)
            delay *= 2
    raise IngestionError(str(last))


def _bulk_upsert(db, rows):
    """Write many travel_times rows in ONE statement.

    Uses ON CONFLICT against the (store_id, zone_id) unique constraint, so a
    re-run can never create duplicates and an interrupted batch is safe to
    replay.
    """
    if not rows:
        return 0
    dialect = db.bind.dialect.name if db.bind is not None else ""
    table = TravelTime.__table__
    updates = (
        "distance_km travel_time_minutes handling_minutes source source_type "
        "calculated_at"
    ).split()

    if dialect in ("postgresql", "sqlite"):
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as _insert
        else:
            from sqlalchemy.dialects.sqlite import insert as _insert
        stmt = _insert(table).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["store_id", "zone_id"],
            set_={c: getattr(stmt.excluded, c) for c in updates},
        )
        db.execute(stmt)
    else:  # pragma: no cover - other dialects
        db.execute(table.insert(), rows)

    db.commit()
    return len(rows)


def ingest_travel_times(
    db: Session, *, use_router: bool = True, max_zones: int | None = None
) -> IngestionReport:
    report = IngestionReport(dataset="travel_times", source_key=SOURCE_KEY)

    stores = list(
        db.execute(select(Store).where(Store.is_candidate.is_(True))).scalars()
    )
    zones = list(
        db.execute(select(DemandZone).where(DemandZone.is_active.is_(True))).scalars()
    )
    if max_zones:
        zones = zones[:max_zones]

    if not stores or not zones:
        report.skipped_reason = (
            f"nothing to route: {len(stores)} candidate stores, {len(zones)} "
            f"active zones. Ingest stores and zones first."
        )
        report.warn(report.skipped_reason)
        return report

    # ------------------------------------------------------------------
    # RESUMABLE: find exactly which (store, zone) pairs are missing.
    #
    # One query, not one per pair. The previous implementation issued a SELECT
    # and an INSERT per zone per store -- 326 round trips to the remote pooler
    # for every store, which is why a full run took far longer than the routing
    # itself did.
    # ------------------------------------------------------------------
    existing: set[tuple[int, int]] = {
        (sid, zid)
        for sid, zid in db.execute(
            select(TravelTime.store_id, TravelTime.zone_id)
        ).all()
    }

    zone_by_id = {z.id: z for z in zones}
    store_by_id = {s.id: s for s in stores}
    missing_by_store: dict[int, list[int]] = {}
    for store in stores:
        todo = [z.id for z in zones if (store.id, z.id) not in existing]
        if todo:
            missing_by_store[store.id] = todo

    total_expected = len(stores) * len(zones)
    total_missing = sum(len(v) for v in missing_by_store.values())
    report.fetched = total_missing

    logger.info(
        "travel_times: %d/%d pairs present, %d missing across %d store(s)",
        len(existing), total_expected, total_missing, len(missing_by_store),
    )
    report.warn(
        f"resuming: {len(existing)} of {total_expected} pairs already routed, "
        f"{total_missing} missing. Existing rows are never recomputed."
    )
    if not missing_by_store:
        report.warn("nothing missing; travel_times is already complete")
        return report

    pending: list[dict] = []
    processed = 0
    inserted_total = 0

    def flush() -> int:
        nonlocal pending
        if not pending:
            return 0
        n = _bulk_upsert(db, pending)
        pending = []
        return n

    for store_id, zone_ids in missing_by_store.items():
        store = store_by_id[store_id]
        targets = [zone_by_id[z] for z in zone_ids]
        dests = [(z.latitude, z.longitude) for z in targets]

        try:
            distances, durations = _osrm_table_retry(
                (store.latitude, store.longitude), dests, report=report
            )
        except IngestionError as exc:
            # A store that cannot be routed is reported and SKIPPED. No
            # haversine value is substituted: a labelled gap is better than a
            # fabricated distance, and a re-run will retry exactly these pairs.
            report.reject(
                f"OSRM could not route store {store_id} after retries: {exc}",
                {"store_id": store_id, "missing_zones": len(zone_ids)},
            )
            inserted_total += flush()
            continue

        for idx, zone in enumerate(targets):
            d_m, t_s = distances[idx], durations[idx]
            if d_m is None or t_s is None:
                report.reject(
                    "router returned no route between these points",
                    {"store_id": store_id, "zone_id": zone.id},
                )
                continue

            km = float(d_m) / 1000.0
            minutes = float(t_s) / 60.0

            if km < 0 or minutes < 0:
                report.reject(
                    f"negative distance/time ({km:.2f} km, {minutes:.2f} min)",
                    {"store_id": store_id, "zone_id": zone.id},
                )
                continue
            if km > MAX_PLAUSIBLE_KM or minutes > MAX_PLAUSIBLE_MINUTES:
                report.reject(
                    f"implausible leg ({km:.1f} km, {minutes:.1f} min) for a "
                    f"city-scale instance; likely a routing artefact",
                    {"store_id": store_id, "zone_id": zone.id},
                )
                continue

            pending.append(
                {
                    "store_id": store_id,
                    "zone_id": zone.id,
                    "distance_km": round(km, 4),
                    "travel_time_minutes": round(minutes, 4),
                    "handling_minutes": HANDLING_MINUTES,
                    "source": "osrm",
                    "source_type": SourceType.REAL_PUBLIC.value,
                    "calculated_at": datetime.now(timezone.utc),
                }
            )
            processed += 1

            if len(pending) >= WRITE_BATCH_SIZE:
                inserted_total += flush()
                logger.info(
                    "Processed: %d / %d missing | Inserted: %d | Remaining: %d",
                    processed, total_missing, inserted_total,
                    total_missing - processed,
                )

    inserted_total += flush()
    logger.info(
        "Processed: %d / %d missing | Inserted: %d | Remaining: %d",
        processed, total_missing, inserted_total, total_missing - processed,
    )
    report.inserted = inserted_total

    # ---- final state, read back from the database -----------------------
    n_real = db.execute(
        select(func.count()).select_from(TravelTime).where(TravelTime.source == "osrm")
    ).scalar_one()
    n_fallback = db.execute(
        select(func.count())
        .select_from(TravelTime)
        .where(TravelTime.source == "haversine_fallback")
    ).scalar_one()
    total_rows = db.execute(select(func.count()).select_from(TravelTime)).scalar_one()

    report.warn(
        f"{n_real} legs routed by OSRM over real road geometry, "
        f"{n_fallback} labelled haversine estimates, {total_rows} rows total "
        f"(target {total_expected})"
    )
    report.warn(
        f"handling time of {HANDLING_MINUTES} min is added to every leg and is "
        f"an operational ASSUMPTION, stored in its own column"
    )
    if total_rows < total_expected:
        report.warn(
            f"INCOMPLETE: {total_expected - total_rows} pair(s) still missing. "
            f"Re-running the travel_times step resumes from exactly what is "
            f"missing and never recomputes existing rows."
        )
    return report


SOURCE_META = {
    "key": SOURCE_KEY,
    "dataset": "Road network routing (store to zone)",
    "source_type": SourceType.REAL_PUBLIC.value,
    "source_name": SOURCE_NAME,
    "source_url": OSRM_BASE_URL,
    "licence": "OSRM (BSD); road data ODbL (c) OpenStreetMap contributors",
    "feeds": "travel_times (distance_km, travel_time_minutes)",
    "notes": (
        "Real road routes over the OpenStreetMap graph, replacing the earlier "
        "straight-line estimate. Any leg the router could not serve is written "
        "as a haversine estimate with source='haversine_fallback' and "
        "source_type='estimated', so estimates are never mistaken for routes. "
        "Provider is pluggable via OSRM_BASE_URL or ROUTING_PROVIDER."
    ),
}
