"""Loading seed data, and building the optimization instance both solvers share.

THE OPTIMIZATION MODEL
======================
One model. Both the QAOA path and the PuLP path receive exactly this instance
and encode exactly these constraints, which is what makes the comparison fair.

Sets
    I   candidate stores
    A   customer areas
    J   products

Data
    f_i        opening cost of store i for one planning period
    cap_i      storage capacity of store i, in volume units
    d_{a,j}    demand quantity for product j in area a
    v_j        volume consumed by one unit of product j
    c_j        supplier cost of one unit of product j
    t_{i,a}    delivery time from store i to area a, in minutes
    T_a        service promise for area a, in minutes
    B          budget for opening costs

Derived per area
    vol_a  = sum_j d_{a,j} * v_j      storage volume needed to serve area a
    val_a  = sum_j d_{a,j} * c_j      supplier value of area a's demand
    qty_a  = sum_j d_{a,j}            demand units in area a
    rev_a  = gross_margin * val_a     margin earned by serving area a

Service-feasible links
    E = { (i, a) : t_{i,a} <= T_a }
    The delivery-time constraint is handled STRUCTURALLY: a link that breaks the
    promise is never created as a variable. A 40-minute delivery is not a bad
    option, it is not an option. This also keeps the QUBO small, which matters
    because every variable is a qubit.

Decision variables
    x_i        1 if candidate store i is opened, else 0
    s_{i,a}    1 if area a is served by store i, else 0   (only for (i,a) in E)

Inventory allocation (the second half of the joint problem)
    inv_{i,j} = sum_{a : (i,a) in E} s_{i,a} * d_{a,j}

    Inventory is a determined quantity, not a free variable. Once you know which
    store serves which area, the stock that store must carry follows exactly.
    This is a deliberate modelling choice: encoding inventory as free integer
    variables would need a binary expansion per store-product pair and push the
    register far past what a statevector simulator can hold. The trade-off is
    documented in the README under Limitations.

Objective (MAXIMISE)
    sum_{(i,a) in E} rev_a * s_{i,a}          margin on demand actually served
  - sum_i f_i * x_i                            opening cost
  - sum_{(i,a) in E} deliv_{i,a} * s_{i,a}     rider cost

    where deliv_{i,a} = rider_cost_per_min * t_{i,a} * orders_a
    and   orders_a    = ceil(qty_a / avg_items_per_order)

Constraints
    C1  single sourcing    sum_{i : (i,a) in E} s_{i,a} <= 1          for all a
    C2  coupling           s_{i,a} <= x_i                             for all (i,a)
    C3  capacity           sum_a vol_a * s_{i,a} <= cap_i * x_i       for all i
    C4  budget             sum_i f_i * x_i <= B
    C5  delivery/service   structural, via E

C1 is "<=" rather than "=" on purpose: leaving an area unserved is allowed. It
simply forfeits rev_a, so the model decides whether serving an area is worth it
instead of being forced to serve everything.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Demand, DemandZone, Product, Store, TravelTime
from app.utils.helpers import area_centroid, delivery_time_min, road_distance_km

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


# ===========================================================================
# The instance
# ===========================================================================
@dataclass
class StoreData:
    id: int
    name: str
    area: str
    latitude: float
    longitude: float
    opening_cost: float
    storage_capacity: float


@dataclass
class ProductData:
    id: int
    name: str
    unit_volume: float
    unit_cost: float


@dataclass
class AreaData:
    name: str
    latitude: float
    longitude: float
    delivery_time_limit: float
    demand_by_product: dict[int, float]
    volume: float          # vol_a
    value: float           # val_a
    quantity: float        # qty_a
    revenue: float         # rev_a
    orders: float


@dataclass
class OptimizationInstance:
    """Everything both solvers need, and nothing solver-specific."""

    stores: list[StoreData]
    products: list[ProductData]
    areas: list[AreaData]
    budget: float

    # (store_id, area_name) -> delivery minutes, for service-feasible links only
    links: dict[tuple[int, str], float]

    # (store_id, area_name) -> rider cost per period
    delivery_cost: dict[tuple[int, str], float]

    # (store_id, area_name) -> how the travel time was obtained:
    #   "osrm"               real route over OSM road geometry
    #   "haversine_fallback" stored estimate (router was unavailable)
    #   "haversine_inline"   computed here because no travel_times row existed
    link_source: dict[tuple[int, str], str] = field(default_factory=dict)

    warnings: list[str] = field(default_factory=list)

    # ================================================================
    # INTEGERISED CONSTRAINT DATA
    #
    # Turning an inequality into an equality with slack variables requires
    # integer coefficients: the slack is itself a bounded integer, encoded in
    # binary. Volumes and costs are floats, so the constraint data is rounded.
    #
    # The rounding direction is chosen so it can only ever make the model
    # STRICTER, never looser:
    #     required volume   rounded UP    (ceil)
    #     available capacity rounded DOWN (floor)
    #     opening cost      rounded UP    (ceil)
    #     budget            rounded DOWN  (floor)
    #
    # So any plan feasible in the rounded model is feasible in the true one. The
    # reverse is not guaranteed, which means we may discard a plan that only
    # just fits. That is the safe direction to err in, and it is reported in the
    # solver details rather than hidden.
    #
    # The OBJECTIVE keeps exact float values; only constraints are integerised.
    # ================================================================
    @property
    def area_volume_int(self) -> dict[str, int]:
        return {a.name: int(math.ceil(a.volume)) for a in self.areas}

    @property
    def store_capacity_int(self) -> dict[int, int]:
        return {s.id: int(math.floor(s.storage_capacity)) for s in self.stores}

    @property
    def store_cost_int(self) -> dict[int, int]:
        return {s.id: int(math.ceil(s.opening_cost)) for s in self.stores}

    @property
    def budget_int(self) -> int:
        return int(math.floor(self.budget))

    def rounding_report(self) -> dict:
        """How much the integerisation changed, so it can be audited."""
        return {
            "area_volume_rounded_up": {
                a.name: round(self.area_volume_int[a.name] - a.volume, 6)
                for a in self.areas
            },
            "store_capacity_rounded_down": {
                s.id: round(s.storage_capacity - self.store_capacity_int[s.id], 6)
                for s in self.stores
            },
            "budget_rounded_down": round(self.budget - self.budget_int, 6),
        }

    # ------------------------------------------------------------ lookups
    @property
    def store_ids(self) -> list[int]:
        return [s.id for s in self.stores]

    @property
    def area_names(self) -> list[str]:
        return [a.name for a in self.areas]

    def store(self, store_id: int) -> StoreData:
        for s in self.stores:
            if s.id == store_id:
                return s
        raise KeyError(f"unknown store id {store_id}")

    def area(self, name: str) -> AreaData:
        for a in self.areas:
            if a.name == name:
                return a
        raise KeyError(f"unknown area {name!r}")

    def servers_of(self, area_name: str) -> list[int]:
        return [i for (i, a) in self.links if a == area_name]

    def served_by(self, store_id: int) -> list[str]:
        return [a for (i, a) in self.links if i == store_id]

    @property
    def total_demand_units(self) -> float:
        return sum(a.quantity for a in self.areas)

    @property
    def total_demand_volume(self) -> float:
        return sum(a.volume for a in self.areas)

    @property
    def total_capacity(self) -> float:
        return sum(s.storage_capacity for s in self.stores)

    def size_summary(self) -> dict:
        n_links = len(self.links)
        return {
            "stores": len(self.stores),
            "areas": len(self.areas),
            "products": len(self.products),
            "service_feasible_links": n_links,
            "binary_variables_before_slack": len(self.stores) + n_links,
            "total_demand_units": round(self.total_demand_units, 3),
            "total_demand_volume": round(self.total_demand_volume, 3),
            "total_capacity": round(self.total_capacity, 3),
            "budget": self.budget,
            "routed_legs": sum(
                1 for v in self.link_source.values() if v == "osrm"
            ),
            "estimated_legs": sum(
                1 for v in self.link_source.values() if v != "osrm"
            ),
        }


class InstanceError(ValueError):
    """Raised when the requested instance cannot be built."""


# ===========================================================================
# Building the instance from the database
# ===========================================================================
def build_instance(
    db: Session,
    budget: float,
    default_delivery_limit: float | None = None,
    store_ids: list[int] | None = None,
    product_ids: list[int] | None = None,
    areas: list[str] | None = None,
) -> OptimizationInstance:
    """Assemble an OptimizationInstance from the current database contents."""
    if budget < 0:
        raise InstanceError("budget must be non-negative")

    fallback_limit = (
        default_delivery_limit
        if default_delivery_limit is not None
        else settings.default_delivery_time_limit
    )
    warnings: list[str] = []

    # ---------------------------------------------------------- stores
    stmt = select(Store).where(Store.is_candidate.is_(True))
    if store_ids:
        stmt = stmt.where(Store.id.in_(store_ids))
    store_rows = list(db.execute(stmt.order_by(Store.id)).scalars())

    if store_ids:
        found = {s.id for s in store_rows}
        missing = [i for i in store_ids if i not in found]
        if missing:
            raise InstanceError(
                f"unknown or non-candidate store ids: {sorted(missing)}"
            )
    if not store_rows:
        raise InstanceError("no candidate stores available")

    stores = [
        StoreData(
            id=s.id,
            name=s.name,
            area=s.area,
            latitude=s.latitude,
            longitude=s.longitude,
            opening_cost=float(s.opening_cost),
            storage_capacity=float(s.storage_capacity),
        )
        for s in store_rows
    ]

    # -------------------------------------------------------- products
    pstmt = select(Product)
    if product_ids:
        pstmt = pstmt.where(Product.id.in_(product_ids))
    product_rows = list(db.execute(pstmt.order_by(Product.id)).scalars())

    if product_ids:
        found = {p.id for p in product_rows}
        missing = [i for i in product_ids if i not in found]
        if missing:
            raise InstanceError(f"unknown product ids: {sorted(missing)}")
    if not product_rows:
        raise InstanceError("no products available")

    products = [
        ProductData(
            id=p.id,
            name=p.name,
            unit_volume=float(p.unit_volume),
            unit_cost=float(p.unit_cost),
        )
        for p in product_rows
    ]
    product_by_id = {p.id: p for p in products}

    # ---------------------------------------------------------- demand
    dstmt = select(Demand).where(Demand.product_id.in_(list(product_by_id)))
    if areas:
        dstmt = dstmt.where(Demand.area.in_(areas))
    demand_rows = list(db.execute(dstmt).scalars())
    if not demand_rows:
        raise InstanceError("no demand rows match the requested instance")

    grouped: dict[str, dict] = {}
    for d in demand_rows:
        entry = grouped.setdefault(
            d.area, {"demand": {}, "limit": float(d.delivery_time_limit)}
        )
        entry["demand"][d.product_id] = entry["demand"].get(d.product_id, 0.0) + float(
            d.demand_quantity
        )
        # An area's promise is the tightest one any of its rows declares, so a
        # mixed table cannot silently relax the service level.
        entry["limit"] = min(entry["limit"], float(d.delivery_time_limit))

    if areas:
        missing = [a for a in areas if a not in grouped]
        if missing:
            raise InstanceError(f"no demand recorded for areas: {sorted(missing)}")

    # ------------------------------------------- area coordinates
    # PREFERRED: a real DemandZone row, whose coordinates come from
    # OpenStreetMap (see services/ingestion/zone_ingestion.py).
    # FALLBACK: the centroid of the stores sharing the area name, which is an
    # approximation and is reported in `warnings`, never hidden.
    zone_rows = {
        z.name: z
        for z in db.execute(
            select(DemandZone).where(DemandZone.name.in_(list(grouped)))
        ).scalars()
    }

    coords_by_area: dict[str, list[tuple[float, float]]] = {}
    for s in stores:
        coords_by_area.setdefault(s.area, []).append((s.latitude, s.longitude))

    area_list: list[AreaData] = []
    zone_id_by_area: dict[str, int] = {}
    for name in sorted(grouped):
        info = grouped[name]
        zone = zone_rows.get(name)
        if zone is not None:
            lat, lon = zone.latitude, zone.longitude
            zone_id_by_area[name] = zone.id
        else:
            pts = coords_by_area.get(name)
            if not pts:
                warnings.append(
                    f"area {name!r} has no demand-zone row and no store sharing "
                    f"its name; located at the centroid of all candidate stores"
                )
                pts = [(s.latitude, s.longitude) for s in stores]
            else:
                warnings.append(
                    f"area {name!r} has no demand-zone row; located at the "
                    f"centroid of the stores in that area (approximation)"
                )
            lat, lon = area_centroid(pts)

        dmap = {pid: q for pid, q in info["demand"].items() if pid in product_by_id}
        vol = sum(q * product_by_id[pid].unit_volume for pid, q in dmap.items())
        val = sum(q * product_by_id[pid].unit_cost for pid, q in dmap.items())
        qty = sum(dmap.values())
        limit = info["limit"] if info["limit"] > 0 else fallback_limit

        area_list.append(
            AreaData(
                name=name,
                latitude=lat,
                longitude=lon,
                delivery_time_limit=limit,
                demand_by_product=dmap,
                volume=vol,
                value=val,
                quantity=qty,
                revenue=settings.gross_margin * val,
                orders=math.ceil(qty / settings.avg_items_per_order) if qty else 0.0,
            )
        )

    # ------------------------------------------- service-feasible links
    # PREFERRED: a routed TravelTime row (OSRM over real OSM road geometry).
    # FALLBACK: the straight-line estimate, counted and reported so a run built
    # on estimates can never be mistaken for one built on real routes.
    routed: dict[tuple[int, int], object] = {}
    if zone_id_by_area:
        for tt in db.execute(
            select(TravelTime).where(
                TravelTime.store_id.in_([s.id for s in stores]),
                TravelTime.zone_id.in_(list(zone_id_by_area.values())),
            )
        ).scalars():
            routed[(tt.store_id, tt.zone_id)] = tt

    links: dict[tuple[int, str], float] = {}
    delivery_cost: dict[tuple[int, str], float] = {}
    link_source: dict[tuple[int, str], str] = {}
    n_routed = n_estimated = 0

    for s in stores:
        for a in area_list:
            zid = zone_id_by_area.get(a.name)
            tt = routed.get((s.id, zid)) if zid is not None else None
            if tt is not None:
                minutes = tt.travel_time_minutes + tt.handling_minutes
                source = tt.source
                if source == "osrm":
                    n_routed += 1
                else:
                    n_estimated += 1
            else:
                minutes = delivery_time_min(
                    s.latitude, s.longitude, a.latitude, a.longitude
                )
                source = "haversine_inline"
                n_estimated += 1

            if minutes <= a.delivery_time_limit:
                links[(s.id, a.name)] = minutes
                delivery_cost[(s.id, a.name)] = (
                    settings.rider_cost_per_min * minutes * a.orders
                )
                link_source[(s.id, a.name)] = source

    if n_routed:
        warnings.append(
            f"{n_routed} store-area legs use real routed travel times (OSRM); "
            f"{n_estimated} use a straight-line estimate"
        )
    elif n_estimated:
        warnings.append(
            f"all {n_estimated} store-area legs use a straight-line ESTIMATE; "
            f"no routed travel times were found for this instance"
        )

    if not links:
        raise InstanceError(
            "no store can reach any area within its delivery time limit; "
            "relax delivery_time_limit or add closer candidate stores"
        )

    uncovered = [a.name for a in area_list if not any(k[1] == a.name for k in links)]
    if uncovered:
        warnings.append(
            f"areas unreachable within their delivery promise and therefore "
            f"never servable: {sorted(uncovered)}"
        )

    affordable = [s for s in stores if s.opening_cost <= budget]
    if not affordable:
        raise InstanceError(
            f"budget {budget} is below the cheapest store opening cost "
            f"{min(s.opening_cost for s in stores)}; no store can be opened"
        )

    return OptimizationInstance(
        stores=stores,
        products=products,
        areas=area_list,
        budget=float(budget),
        links=links,
        delivery_cost=delivery_cost,
        link_source=link_source,
        warnings=warnings,
    )


# ===========================================================================
# Seeding
# ===========================================================================
def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"seed file not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def seed_database(db: Session, *, reset: bool = False, data_dir: Path | None = None) -> dict:
    """Load the CSV seed files into the database.

    Idempotent: re-running updates existing rows rather than duplicating them.
    """
    folder = data_dir or DATA_DIR

    if reset:
        db.query(Demand).delete()
        db.query(Product).delete()
        db.query(Store).delete()
        db.commit()

    counts = {"stores": 0, "products": 0, "demand": 0}

    # ---- stores -------------------------------------------------------
    for row in _read_csv(folder / "seed_data.csv"):
        existing = db.execute(
            select(Store).where(
                Store.name == row["name"], Store.area == row["area"]
            )
        ).scalar_one_or_none()
        payload = dict(
            name=row["name"],
            area=row["area"],
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            opening_cost=float(row["opening_cost"]),
            storage_capacity=float(row["storage_capacity"]),
            platform=row.get("platform") or None,
            is_candidate=str(row.get("is_candidate", "TRUE")).strip().upper()
            in {"TRUE", "1", "YES"},
            data_source=row.get("data_source", "DEMO_ASSUMPTION"),
        )
        if existing:
            for k, v in payload.items():
                setattr(existing, k, v)
        else:
            db.add(Store(**payload))
            counts["stores"] += 1
    db.commit()

    # ---- products -----------------------------------------------------
    key_to_product: dict[str, Product] = {}
    for row in _read_csv(folder / "demo_products.csv"):
        existing = db.execute(
            select(Product).where(Product.name == row["name"])
        ).scalar_one_or_none()
        payload = dict(
            name=row["name"],
            category=row["category"],
            unit_volume=float(row["unit_volume"]),
            unit_cost=float(row["unit_cost"]),
            data_source=row.get("data_source", "DEMO_ASSUMPTION"),
        )
        if existing:
            for k, v in payload.items():
                setattr(existing, k, v)
            key_to_product[row["product_key"]] = existing
        else:
            obj = Product(**payload)
            db.add(obj)
            counts["products"] += 1
            key_to_product[row["product_key"]] = obj
    db.commit()

    # ---- demand -------------------------------------------------------
    for row in _read_csv(folder / "demo_demand.csv"):
        product = key_to_product.get(row["product_key"])
        if product is None:
            continue
        existing = db.execute(
            select(Demand).where(
                Demand.area == row["area"], Demand.product_id == product.id
            )
        ).scalar_one_or_none()
        payload = dict(
            area=row["area"],
            product_id=product.id,
            demand_quantity=float(row["demand_quantity"]),
            delivery_time_limit=float(row["delivery_time_limit"]),
            data_source=row.get("data_source", "DEMO_ASSUMPTION"),
        )
        if existing:
            for k, v in payload.items():
                setattr(existing, k, v)
        else:
            db.add(Demand(**payload))
            counts["demand"] += 1
    db.commit()

    return counts


def dev_instance_ids(db: Session) -> dict:
    """The small 3x3x3 development instance the README tells you to start with.

    Three candidate stores, three areas, three products. Small enough that the
    QUBO fits comfortably in a simulator and the answer can be checked by hand.
    """
    all_stores = list(
        db.execute(
            select(Store).where(Store.is_candidate.is_(True)).order_by(Store.id)
        ).scalars()
    )
    # One store per distinct area. Taking the first three rows by id would pick
    # three Venkata Nagar stores and collapse the instance to a single area,
    # leaving no siting decision to make.
    picked: dict[str, Store] = {}
    for s in all_stores:
        if s.area not in picked:
            picked[s.area] = s
        if len(picked) == 3:
            break

    products = list(db.execute(select(Product).order_by(Product.id).limit(3)).scalars())
    return {
        "store_ids": [s.id for s in picked.values()],
        "product_ids": [p.id for p in products],
        "areas": sorted(picked),
    }


def distance_report(instance: OptimizationInstance) -> list[dict]:
    """Every store-area pair with its distance, time and service verdict."""
    out = []
    for s in instance.stores:
        for a in instance.areas:
            minutes = delivery_time_min(s.latitude, s.longitude, a.latitude, a.longitude)
            out.append(
                {
                    "store_id": s.id,
                    "store_name": s.name,
                    "area": a.name,
                    "road_distance_km": round(
                        road_distance_km(s.latitude, s.longitude, a.latitude, a.longitude),
                        3,
                    ),
                    "delivery_time_min": round(minutes, 2),
                    "delivery_time_limit": a.delivery_time_limit,
                    "within_service_limit": minutes <= a.delivery_time_limit,
                }
            )
    return out


def suggest_instance(
    db: Session,
    *,
    delivery_limit: float = 15.0,
    max_stores: int = 4,
    max_zones: int = 4,
) -> dict:
    """Propose a small, solvable instance from whatever is currently ingested.

    Selection rules, all data-driven:
      * a zone must actually have demand rows,
      * it must be reachable by at least one routed leg inside the promise,
      * zones with 2-5 reachable stores are preferred, because one server means
        no assignment decision and many servers blow up the qubit count.

    Nothing here is hardcoded to a particular store or area name.
    """
    from sqlalchemy import func

    from app.models import DemandZone, TravelTime

    zones_with_demand = {
        row[0] for row in db.execute(select(Demand.area).distinct()).all()
    }
    if not zones_with_demand:
        raise InstanceError("no demand rows exist; run the ingestion pipeline first")

    reach_expr = TravelTime.travel_time_minutes + TravelTime.handling_minutes
    counts = db.execute(
        select(TravelTime.zone_id, func.count(TravelTime.store_id))
        .where(reach_expr <= delivery_limit)
        .group_by(TravelTime.zone_id)
    ).all()
    if not counts:
        raise InstanceError(
            f"no store reaches any zone within {delivery_limit} minutes; "
            f"raise the limit or ingest travel times"
        )

    zone_rows = {
        z.id: z
        for z in db.execute(
            select(DemandZone).where(DemandZone.id.in_([c[0] for c in counts]))
        ).scalars()
    }

    ranked = sorted(
        (
            (zid, n)
            for zid, n in counts
            if zid in zone_rows and zone_rows[zid].name in zones_with_demand
        ),
        key=lambda t: (not (2 <= t[1] <= 5), -t[1]),
    )
    if not ranked:
        raise InstanceError(
            "no zone has both demand and a reachable store within the limit"
        )

    chosen_zone_ids = [zid for zid, _ in ranked[:max_zones]]
    chosen_names = [zone_rows[z].name for z in chosen_zone_ids]

    store_ids = sorted(
        {
            tt.store_id
            for tt in db.execute(
                select(TravelTime).where(
                    TravelTime.zone_id.in_(chosen_zone_ids),
                    reach_expr <= delivery_limit,
                )
            ).scalars()
        }
    )[:max_stores]

    product_ids = [
        p.id for p in db.execute(select(Product).order_by(Product.id)).scalars()
    ]

    return {
        "store_ids": store_ids,
        "areas": chosen_names,
        "product_ids": product_ids,
        "delivery_time_limit": delivery_limit,
        "rationale": (
            f"{len(chosen_names)} zone(s) with demand and a routed leg inside "
            f"{delivery_limit} min, served by {len(store_ids)} candidate store(s); "
            f"all {len(product_ids)} catalogue products included"
        ),
    }
