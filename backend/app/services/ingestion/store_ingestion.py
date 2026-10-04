"""Candidate dark-store locations from OpenStreetMap.

WHAT THIS IS, AND WHAT IT IS NOT
================================
These are REAL retail outlets mapped in OpenStreetMap inside the Puducherry
mainland: supermarkets, convenience stores and general stores, with coordinates
contributed and verifiable by anyone.

They are used as CANDIDATE DARK-STORE SITES. They are NOT claimed to be
operating dark stores. Quick-commerce dark stores are deliberately unmarked and
are not tagged as such in OSM -- a query for Blinkit/Zepto/Instamart brands in
Puducherry returns nothing. Any dataset claiming to list live Puducherry dark
stores with addresses would need to be verified before use.

What IS real here: name, coordinates, shop type, OSM id, licence.
What is NOT real: opening cost and storage capacity. Those require operator
data, so they are carried over as clearly-labelled prototype assumptions and
their provenance columns say `synthetic`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SourceType, Store
from app.services.ingestion.base import (
    PUDUCHERRY_BBOX,
    IngestionReport,
    inside_bbox,
    overpass,
    today_iso,
    utcnow_iso,
    valid_coordinate,
)

SOURCE_KEY = "osm_stores"
SOURCE_NAME = "OpenStreetMap (Overpass API)"
SOURCE_URL = "https://overpass-api.de/api/interpreter"
LICENCE = "ODbL 1.0 - (c) OpenStreetMap contributors"

S, W, N, E = PUDUCHERRY_BBOX

# Retail outlets that could plausibly host or neighbour a dark store.
QUERY = f"""
[out:json][timeout:180];
(
  node({S},{W},{N},{E})["shop"~"^(supermarket|convenience|general|grocery)$"];
  way({S},{W},{N},{E})["shop"~"^(supermarket|convenience|general|grocery)$"];
);
out center tags;
"""

# ---------------------------------------------------------------------------
# PROTOTYPE ASSUMPTIONS -- NOT REAL DATA.
#
# Opening cost and storage capacity cannot be observed from OSM. Rather than
# invent a different number per store, they are derived from the shop type by a
# single documented rule, and every affected column is marked `synthetic`.
#
# Daily opening cost covers rent + staff + utilities + amortised fit-out, at the
# scale established earlier in this project for a Puducherry dark store.
# ---------------------------------------------------------------------------
ASSUMED_BY_SHOP_TYPE = {
    "supermarket": {"opening_cost": 9200.0, "storage_capacity": 4200.0},
    "general": {"opening_cost": 7800.0, "storage_capacity": 3600.0},
    "grocery": {"opening_cost": 7400.0, "storage_capacity": 3400.0},
    "convenience": {"opening_cost": 6600.0, "storage_capacity": 2800.0},
}
ASSUMPTION_NOTE = (
    "opening_cost and storage_capacity are PROTOTYPE ASSUMPTIONS keyed to OSM "
    "shop type; they are not operator data"
)


def _area_for(lat: float, lon: float, tags: dict) -> str:
    """Best available area label, preferring what OSM actually recorded."""
    for key in ("addr:suburb", "addr:city", "addr:district", "addr:neighbourhood"):
        if tags.get(key):
            return str(tags[key])
    return "Puducherry"


def ingest_stores(db: Session, *, use_cache: bool = True) -> IngestionReport:
    report = IngestionReport(dataset="stores", source_key=SOURCE_KEY)

    payload = overpass(QUERY, cache_name="osm_stores", use_cache=use_cache)
    elements = payload.get("elements", [])
    report.fetched = len(elements)

    seen_external: set[str] = set()
    seen_coords: set[tuple[float, float]] = set()
    verified = utcnow_iso()

    for el in elements:
        tags = el.get("tags") or {}
        osm_id = f"osm:{el.get('type')}/{el.get('id')}"

        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")

        ok, why = valid_coordinate(lat, lon)
        if not ok:
            report.reject(why, {"osm_id": osm_id, "tags": tags})
            continue
        lat, lon = float(lat), float(lon)

        # Puducherry UT includes Mahé (Kerala) and Yanam (AP). Anything outside
        # the mainland bbox is a different landmass and would wreck routing.
        if not inside_bbox(lat, lon):
            report.reject(
                f"coordinate ({lat:.4f},{lon:.4f}) outside the Puducherry "
                f"mainland bounding box (likely the Mahe or Yanam exclave)",
                {"osm_id": osm_id, "name": tags.get("name")},
            )
            continue

        name = (tags.get("name") or "").strip()
        if not name:
            report.reject(
                "unnamed outlet; cannot be presented as an identifiable site",
                {"osm_id": osm_id, "lat": lat, "lon": lon},
            )
            continue

        if osm_id in seen_external:
            report.reject("duplicate OSM id within this feed", {"osm_id": osm_id})
            continue

        coord_key = (round(lat, 6), round(lon, 6))
        if coord_key in seen_coords:
            report.reject(
                "duplicate coordinate: another outlet is already mapped at this "
                "exact point",
                {"osm_id": osm_id, "name": name, "lat": lat, "lon": lon},
            )
            continue

        seen_external.add(osm_id)
        seen_coords.add(coord_key)

        shop = tags.get("shop", "convenience")
        assumed = ASSUMED_BY_SHOP_TYPE.get(shop, ASSUMED_BY_SHOP_TYPE["convenience"])

        values = dict(
            name=name[:120],
            area=_area_for(lat, lon, tags)[:120],
            latitude=lat,
            longitude=lon,
            platform=tags.get("brand") or tags.get("operator") or "unbranded",
            is_candidate=True,
            data_source="OSM_REAL_LOCATION+SYNTHETIC_COST",
            location_source_type=SourceType.REAL_PUBLIC.value,
            source_name=SOURCE_NAME,
            source_url=f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}",
            source_date=today_iso(),
            verified_at=verified,
            active_status="mapped_in_osm",
            # The honest part: location is real, economics are not.
            opening_cost=assumed["opening_cost"],
            storage_capacity=assumed["storage_capacity"],
            cost_source_type=SourceType.SYNTHETIC.value,
            capacity_source_type=SourceType.SYNTHETIC.value,
        )

        existing = db.execute(
            select(Store).where(Store.external_id == osm_id)
        ).scalar_one_or_none()

        if existing:
            for k, v in values.items():
                setattr(existing, k, v)
            report.updated += 1
        else:
            db.add(Store(external_id=osm_id, **values))
            report.inserted += 1

    db.commit()
    report.warn(ASSUMPTION_NOTE)
    report.warn(
        "These are OSM-mapped retail outlets used as CANDIDATE sites. They are "
        "not verified operating dark stores."
    )
    return report


SOURCE_META = {
    "key": SOURCE_KEY,
    "dataset": "Candidate dark-store locations",
    "source_type": SourceType.REAL_PUBLIC.value,
    "source_name": SOURCE_NAME,
    "source_url": SOURCE_URL,
    "licence": LICENCE,
    "feeds": "stores (location only)",
    "notes": (
        "Real OSM retail outlets inside the Puducherry mainland bounding box, "
        "used as candidate dark-store sites. Coordinates, names and shop types "
        "are real. Opening cost and storage capacity are prototype assumptions "
        "and are marked synthetic on every row. No quick-commerce operator "
        "tags dark stores in OSM, so no store here is claimed to be an "
        "operating dark store."
    ),
}
