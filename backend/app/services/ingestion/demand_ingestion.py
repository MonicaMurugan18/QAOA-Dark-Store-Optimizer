"""Demand generation.

THIS PRODUCES A PROXY, NOT CUSTOMER DEMAND
==========================================
No legitimate source of Puducherry quick-commerce order data is publicly
available. Platform order histories are private commercial data and are not
scraped here. So until authorised operator data arrives, demand is ESTIMATED
from population by a documented, configurable formula, and every row it writes
is labelled `proxy`/`estimated`.

Nothing in this system may describe the output as actual customer orders.

DEMAND_MODE
===========
    population_proxy   (default) derive demand from zone population
    historical_orders  consume a real order table; raises until one exists

THE FORMULA
===========
    zone_population
      x ADOPTION_RATE          share of residents who order from quick commerce
      x ORDERS_PER_USER_DAY    orders placed per adopting resident per day
      = zone_orders_per_day

    zone_orders_per_day x ITEMS_PER_ORDER x product_share(p)
      = demand_units(zone, product)

Every coefficient is an assumption with a stated default, overridable by
environment variable. `product_share` is derived from the real catalogue's
category mix, so the split across products reflects a real catalogue even though
the overall level is estimated.

POPULATION ALLOCATION
=====================
Ward-level Census figures are not reachable (see zone_ingestion). When a zone has
no population of its own, commune population is allocated across zones that lack
a figure, evenly. That is an explicit modelling assumption, recorded as
`estimated`, and the API reports how many zones were allocated this way.
"""

from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Demand, DemandZone, Product, SourceType
from app.services.ingestion.base import IngestionReport

SOURCE_KEY = "demand_proxy"

DEMAND_MODE = os.environ.get("DEMAND_MODE", "population_proxy")

# ---- configurable proxy coefficients (all assumptions) --------------------
ADOPTION_RATE = float(os.environ.get("DEMAND_ADOPTION_RATE", "0.06"))
ORDERS_PER_USER_DAY = float(os.environ.get("DEMAND_ORDERS_PER_USER_DAY", "0.35"))
ITEMS_PER_ORDER = float(os.environ.get("DEMAND_ITEMS_PER_ORDER", "5.0"))
DEFAULT_DELIVERY_LIMIT = float(os.environ.get("DEFAULT_DELIVERY_TIME_LIMIT", "15.0"))

#: Commune population to spread over zones that have no figure of their own.
#: Census of India 2011 via Wikidata. Used only for allocation, never presented
#: as a ward-level observation.
FALLBACK_COMMUNE_POPULATION = float(
    os.environ.get("DEMAND_FALLBACK_COMMUNE_POPULATION", "244377")
)
FALLBACK_COMMUNE_NAME = "Puducherry municipality (Census of India 2011)"

#: WHICH OSM PLACE TYPES COUNT AS A DEMAND ZONE.
#:
#: This is a modelling decision, and it matters. The OSM extract for this
#: bounding box contains 102 nodes tagged `neighbourhood` and 15 tagged
#: `quarter` -- but inspecting them shows they are almost entirely AUROVILLE
#: SETTLEMENT PLOTS (Promesse, Udayan, Certitude, Adventure, ...), each home to
#: a handful of residents in an intentional community. The Puducherry city areas
#: a quick-commerce operator would actually serve (Lawspet, Mudaliarpet,
#: Reddiarpalayam, Grand Bazaar, Ariyankuppam, ...) are tagged `suburb`, `town`
#: or `village`.
#:
#: Allocating municipal population evenly across all 163 nodes would hand ~63%
#: of the city's residents to Auroville plots, which is simply wrong. So the
#: proxy defaults to the place types that represent real residential areas at
#: city scale. Auroville itself is tagged `town` and keeps its own sourced
#: Census figure, so it is still represented -- at its real size.
#:
#: Override with DEMAND_ZONE_TYPES to include every node.
DEMAND_ZONE_TYPES = {
    t.strip()
    for t in os.environ.get("DEMAND_ZONE_TYPES", "suburb,town,village").split(",")
    if t.strip()
}


class DemandModeError(RuntimeError):
    """Raised when a demand mode is requested that has no data behind it."""


def product_shares(products: list[Product]) -> dict[int, float]:
    """Split demand across products using the real catalogue's category mix.

    Each category gets an equal share of total demand, then that share is split
    evenly among the products in it. This keeps a catalogue with 9 personal-care
    items from swamping a catalogue with 2 dairy items, and it uses the REAL
    category labels rather than an invented ranking.
    """
    by_category: dict[str, list[Product]] = {}
    for p in products:
        by_category.setdefault(p.category or "Uncategorised", []).append(p)
    if not by_category:
        return {}
    cat_share = 1.0 / len(by_category)
    shares: dict[int, float] = {}
    for items in by_category.values():
        per = cat_share / len(items)
        for p in items:
            shares[p.id] = per
    return shares


def ingest_demand(
    db: Session,
    *,
    mode: str | None = None,
    zone_limit: int | None = None,
    product_limit: int | None = None,
) -> IngestionReport:
    report = IngestionReport(dataset="demand", source_key=SOURCE_KEY)
    mode = mode or DEMAND_MODE

    if mode == "historical_orders":
        raise DemandModeError(
            "DEMAND_MODE=historical_orders requires an authorised order dataset, "
            "which this project does not have. No public source of Puducherry "
            "quick-commerce order data exists, and platform order data is "
            "private. Load real orders into an `orders` table and implement the "
            "reader here; the rest of the pipeline is ready for it."
        )
    if mode != "population_proxy":
        raise DemandModeError(f"unknown DEMAND_MODE {mode!r}")

    all_zones = list(
        db.execute(
            select(DemandZone).where(DemandZone.is_active.is_(True)).order_by(DemandZone.id)
        ).scalars()
    )
    zones = [z for z in all_zones if (z.zone_type or "") in DEMAND_ZONE_TYPES]
    excluded = len(all_zones) - len(zones)
    if excluded:
        report.warn(
            f"{excluded} of {len(all_zones)} zones were excluded from demand "
            f"because their OSM place type is not in {sorted(DEMAND_ZONE_TYPES)}. "
            f"In this extract those are predominantly Auroville settlement plots "
            f"rather than Puducherry city areas. Override with DEMAND_ZONE_TYPES."
        )
    products = list(db.execute(select(Product).order_by(Product.id)).scalars())
    if zone_limit:
        zones = zones[:zone_limit]
    if product_limit:
        products = products[:product_limit]

    if not zones or not products:
        report.skipped_reason = (
            f"cannot build demand: {len(zones)} zones, {len(products)} products. "
            f"Ingest zones and products first."
        )
        report.warn(report.skipped_reason)
        return report

    # --- population allocation -------------------------------------------
    sourced = [z for z in zones if z.population and z.population > 0]
    unsourced = [z for z in zones if not z.population or z.population <= 0]

    allocated = 0.0
    if unsourced:
        allocated = FALLBACK_COMMUNE_POPULATION / len(unsourced)
        report.warn(
            f"{len(unsourced)} of {len(zones)} zones have no sourced population. "
            f"{FALLBACK_COMMUNE_POPULATION:,.0f} ({FALLBACK_COMMUNE_NAME}) was "
            f"allocated evenly across them at {allocated:,.0f} per zone. This is "
            f"an ESTIMATE, not a ward-level observation."
        )
    if sourced:
        report.warn(
            f"{len(sourced)} zone(s) used a population figure sourced directly "
            f"for that place."
        )

    shares = product_shares(products)
    report.fetched = len(zones) * len(products)

    for zone in zones:
        population = (
            float(zone.population)
            if zone.population and zone.population > 0
            else allocated
        )
        if population <= 0:
            report.reject(
                "no population available and no allocation possible",
                {"zone": zone.name},
            )
            continue

        orders_per_day = population * ADOPTION_RATE * ORDERS_PER_USER_DAY
        items_per_day = orders_per_day * ITEMS_PER_ORDER

        for product in products:
            share = shares.get(product.id, 0.0)
            qty = round(items_per_day * share, 2)
            if qty < 0:
                report.reject(
                    f"negative demand {qty}", {"zone": zone.name, "product": product.name}
                )
                continue

            values = dict(
                area=zone.name,
                product_id=product.id,
                demand_quantity=qty,
                delivery_time_limit=DEFAULT_DELIVERY_LIMIT,
                data_source="POPULATION_PROXY_ESTIMATED",
            )
            existing = db.execute(
                select(Demand).where(
                    Demand.area == zone.name, Demand.product_id == product.id
                )
            ).scalar_one_or_none()
            if existing:
                for k, v in values.items():
                    setattr(existing, k, v)
                report.updated += 1
            else:
                db.add(Demand(**values))
                report.inserted += 1

    db.commit()
    report.warn(
        f"formula: population x {ADOPTION_RATE} adoption x "
        f"{ORDERS_PER_USER_DAY} orders/user/day x {ITEMS_PER_ORDER} items/order, "
        f"split by the real catalogue's category mix"
    )
    report.warn(
        "THIS IS A DEMAND PROXY. It is derived from population, not from "
        "observed customer orders, and must never be described as real demand."
    )
    return report


SOURCE_META = {
    "key": SOURCE_KEY,
    "dataset": "Demand (population-derived)",
    "source_type": SourceType.PROXY.value,
    "source_name": "Population proxy model (DEMAND_MODE=population_proxy)",
    "source_url": None,
    "licence": "derived",
    "feeds": "demand",
    "notes": (
        "NOT customer orders. Demand is estimated from zone population by a "
        "documented, configurable formula: population x adoption rate x orders "
        "per user per day x items per order, split across products by the real "
        "catalogue's category mix. No public source of Puducherry quick-commerce "
        "order data exists and platform order data is private, so this proxy "
        "stands in until authorised operator data is loaded. Switch with "
        "DEMAND_MODE=historical_orders once an orders table exists."
    ),
}
