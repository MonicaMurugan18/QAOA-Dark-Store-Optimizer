"""Demand zones from OpenStreetMap, population from Census-derived sources.

TWO DIFFERENT PROVENANCES IN ONE TABLE
======================================
A demand zone's GEOMETRY and its POPULATION come from different places and carry
different confidence, so they are recorded separately.

GEOMETRY  real_public. OSM place nodes (suburb / neighbourhood / quarter /
          village / town) inside the Puducherry mainland. Real coordinates.

POPULATION official where a source publishes it for that exact place; otherwise
          NULL. It is never guessed.

          What is actually obtainable:
            - Census of India 2011 figures for Puducherry and Uzhavarkarai
              (Ozhukarai) communes, via Wikidata, which cites the Census.
            - OSM `population` tags, which are sparse.

          WARD-LEVEL POPULATION IS NOT AVAILABLE. censusindia.gov.in was
          unreachable from this environment and api.data.gov.in refused the
          connection. So zone-level population is left NULL unless a source
          names that place, and the demand proxy (see demand_ingestion.py) has
          to allocate commune population across zones by a documented,
          configurable rule which is labelled `estimated` -- not `official`.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DemandZone, SourceType
from app.services.ingestion.base import (
    PUDUCHERRY_BBOX,
    RAW_DIR,
    IngestionError,
    IngestionReport,
    http_get,
    inside_bbox,
    overpass,
    today_iso,
    valid_coordinate,
)

SOURCE_KEY = "osm_zones"
POP_SOURCE_KEY = "census_population"

SOURCE_NAME = "OpenStreetMap (Overpass API)"
POP_SOURCE_NAME = "Census of India 2011, via Wikidata (P1082)"
POP_SOURCE_URL = "https://query.wikidata.org/sparql"
POP_SOURCE_DATE = "2011"  # the Census year, NOT the download date

S, W, N, E = PUDUCHERRY_BBOX

ZONE_QUERY = f"""
[out:json][timeout:180];
(
  node({S},{W},{N},{E})["place"~"^(city|town|suburb|neighbourhood|quarter|village)$"];
);
out tags;
"""

# Place types worth treating as demand zones. "city" is the whole of Puducherry
# and would double-count every other zone, so it is excluded.
USABLE_PLACES = {"suburb", "neighbourhood", "quarter", "town", "village"}

WIKIDATA_SPARQL = """SELECT ?placeLabel ?pop ?lat ?lon WHERE {
  ?place wdt:P131* wd:Q66743 ; wdt:P1082 ?pop ; p:P625 ?st .
  ?st psv:P625 ?v . ?v wikibase:geoLatitude ?lat ; wikibase:geoLongitude ?lon .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} LIMIT 200"""


def fetch_population_reference(*, use_cache: bool = True) -> list[dict]:
    """Census-derived population for named places in the Puducherry UT.

    Returns [] and records the reason if the endpoint is unavailable; it never
    substitutes a made-up figure.
    """
    cache = RAW_DIR / "wikidata_population.json"
    if use_cache and cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
    else:
        import urllib.parse

        url = "https://query.wikidata.org/sparql?query=" + urllib.parse.quote(
            WIKIDATA_SPARQL
        )
        raw = http_get(url, timeout=120, accept="application/sparql-results+json")
        data = json.loads(raw)
        cache.write_text(json.dumps(data, indent=1), encoding="utf-8")

    out = []
    for row in data.get("results", {}).get("bindings", []):
        try:
            out.append(
                {
                    "name": row["placeLabel"]["value"],
                    "population": float(row["pop"]["value"]),
                    "lat": float(row["lat"]["value"]),
                    "lon": float(row["lon"]["value"]),
                }
            )
        except (KeyError, ValueError):
            continue
    return out


def ingest_zones(db: Session, *, use_cache: bool = True) -> IngestionReport:
    report = IngestionReport(dataset="demand_zones", source_key=SOURCE_KEY)

    payload = overpass(ZONE_QUERY, cache_name="osm_zones", use_cache=use_cache)
    elements = payload.get("elements", [])
    report.fetched = len(elements)

    # --- population reference (optional; absence is reported, not faked) ---
    pop_lookup: dict[str, dict] = {}
    try:
        for row in fetch_population_reference(use_cache=use_cache):
            pop_lookup[row["name"].strip().lower()] = row
        report.warn(
            f"population reference loaded for {len(pop_lookup)} named places "
            f"(Census of India 2011 via Wikidata)"
        )
    except IngestionError as exc:
        report.warn(
            f"population reference unavailable ({exc}); zone population will be "
            f"left NULL rather than estimated at this stage"
        )

    seen_ids: set[str] = set()
    seen_names: set[str] = set()

    for el in elements:
        tags = el.get("tags") or {}
        osm_id = f"osm:{el.get('type')}/{el.get('id')}"
        place = tags.get("place")
        name = (tags.get("name") or "").strip()

        if place not in USABLE_PLACES:
            report.reject(
                f"place type {place!r} is not a demand zone "
                f"(a 'city' node covers the whole study area)",
                {"osm_id": osm_id, "name": name},
            )
            continue

        if not name:
            report.reject("unnamed place", {"osm_id": osm_id})
            continue

        ok, why = valid_coordinate(el.get("lat"), el.get("lon"))
        if not ok:
            report.reject(why, {"osm_id": osm_id, "name": name})
            continue
        lat, lon = float(el["lat"]), float(el["lon"])

        if not inside_bbox(lat, lon):
            report.reject(
                f"coordinate ({lat:.4f},{lon:.4f}) outside the Puducherry mainland",
                {"osm_id": osm_id, "name": name},
            )
            continue

        if osm_id in seen_ids:
            report.reject("duplicate OSM id", {"osm_id": osm_id})
            continue
        key = name.strip().lower()
        if key in seen_names:
            report.reject(
                "duplicate zone name in this feed", {"osm_id": osm_id, "name": name}
            )
            continue
        seen_ids.add(osm_id)
        seen_names.add(key)

        # --- population: only when a source names THIS place ---------------
        population = None
        pop_type = None
        pop_source = None
        pop_date = None
        if tags.get("population"):
            try:
                population = float(str(tags["population"]).replace(",", ""))
                pop_type = SourceType.REAL_PUBLIC.value
                pop_source = "OpenStreetMap population tag"
                pop_date = today_iso()
            except ValueError:
                report.reject(
                    f"unparseable OSM population tag {tags['population']!r}",
                    {"osm_id": osm_id, "name": name},
                )
        if population is None and key in pop_lookup:
            population = pop_lookup[key]["population"]
            pop_type = SourceType.OFFICIAL.value
            pop_source = POP_SOURCE_NAME
            pop_date = POP_SOURCE_DATE

        if population is not None and population < 0:
            report.reject(
                f"negative population {population}", {"osm_id": osm_id, "name": name}
            )
            population = None
            pop_type = pop_source = pop_date = None

        values = dict(
            name=name[:160],
            zone_type=place,
            latitude=lat,
            longitude=lon,
            population=population,
            geometry_source_type=SourceType.REAL_PUBLIC.value,
            geometry_source=SOURCE_NAME,
            population_source_type=pop_type,
            population_source=pop_source,
            population_source_date=pop_date,
            is_active=True,
        )

        existing = db.execute(
            select(DemandZone).where(DemandZone.external_id == osm_id)
        ).scalar_one_or_none()
        if existing:
            for k, v in values.items():
                setattr(existing, k, v)
            report.updated += 1
        else:
            db.add(DemandZone(external_id=osm_id, **values))
            report.inserted += 1

    db.commit()

    with_pop = db.execute(
        select(DemandZone).where(DemandZone.population.isnot(None))
    ).scalars()
    n_with_pop = len(list(with_pop))
    report.warn(
        f"{n_with_pop} zone(s) have a sourced population figure. Ward-level "
        f"Census data is not reachable from this environment "
        f"(censusindia.gov.in timed out, api.data.gov.in refused the "
        f"connection), so the rest are NULL and the demand proxy must allocate."
    )
    return report


SOURCE_META = {
    "key": SOURCE_KEY,
    "dataset": "Demand zones (geometry)",
    "source_type": SourceType.REAL_PUBLIC.value,
    "source_name": SOURCE_NAME,
    "source_url": "https://overpass-api.de/api/interpreter",
    "licence": "ODbL 1.0 - (c) OpenStreetMap contributors",
    "feeds": "demand_zones (name, coordinates, type)",
    "notes": (
        "Real OSM place nodes inside the Puducherry mainland. Geometry is real "
        "and verifiable. Population is tracked separately and is NULL unless a "
        "source names that exact place."
    ),
}

POPULATION_SOURCE_META = {
    "key": POP_SOURCE_KEY,
    "dataset": "Population (demand proxy input)",
    "source_type": SourceType.OFFICIAL.value,
    "source_name": POP_SOURCE_NAME,
    "source_url": POP_SOURCE_URL,
    "licence": "CC0 (Wikidata); underlying figures (c) Census of India",
    "feeds": "demand_zones.population",
    "notes": (
        "Census of India 2011 figures, retrieved through Wikidata which cites "
        "the Census. The source_date is 2011 -- the Census year -- not the "
        "download date. Population is a DEMAND PROXY, never customer demand. "
        "Only commune-level figures are available; ward-level Census data could "
        "not be reached (censusindia.gov.in timed out, api.data.gov.in refused "
        "the connection)."
    ),
}
