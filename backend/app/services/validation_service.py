"""Independent validation and metric computation for a candidate solution.

WHY THIS IS A SEPARATE MODULE
=============================
Neither solver validates its own answer. A QUBO can only be *penalised* for
breaking a constraint, so a QAOA bitstring may well be infeasible; and an MILP
solver's own "optimal" status only means optimal for the model it was handed.

Everything here re-derives metrics and re-checks every constraint from the RAW
instance data -- store costs, capacities, demand, delivery times. It never reads
the QUBO matrix, the penalty weight, or PuLP's status. That independence is what
makes a reported violation meaningful.

Both solvers call `evaluate_solution`, so every metric in the comparison is
computed by identical code. Any difference in the numbers comes from the
solutions, never from the measurement.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.data_service import OptimizationInstance
from app.utils.helpers import delivery_time_min, safe_div

# Tolerance for floating-point comparisons on money and volume.
EPS = 1e-6


@dataclass
class SolutionMetrics:
    objective_value: float
    revenue_captured: float
    opening_cost: float
    delivery_cost: float
    demand_units_total: float
    demand_units_served: float
    service_level: float
    budget_used: float
    storage_used: float
    storage_available: float
    storage_utilization: float
    selected_stores: list[int]
    selected_store_names: list[str]
    area_assignments: list[dict]
    inventory_allocation: list[dict]
    feasible: bool
    checks: list[dict]
    violations: list[str]

    def as_result_payload(self) -> dict:
        return {
            "objective_value": round(self.objective_value, 4),
            "customers_served": round(self.demand_units_served, 4),
            "demand_units_total": round(self.demand_units_total, 4),
            "demand_units_served": round(self.demand_units_served, 4),
            "service_level": round(self.service_level, 6),
            "budget_used": round(self.budget_used, 4),
            "storage_used": round(self.storage_used, 4),
            "storage_available": round(self.storage_available, 4),
            "storage_utilization": round(self.storage_utilization, 6),
            "selected_stores": self.selected_stores,
            "selected_store_names": self.selected_store_names,
            "area_assignments": self.area_assignments,
            "inventory_allocation": self.inventory_allocation,
            "validation": {
                "feasible": self.feasible,
                "checks": self.checks,
                "violations": self.violations,
            },
        }


def evaluate_solution(
    instance: OptimizationInstance,
    selected_stores: list[int],
    assignment: dict[str, int | None],
    raw_link_flags: dict[tuple[int, str], int] | None = None,
) -> SolutionMetrics:
    """Score and validate one candidate plan.

    selected_stores  store ids the solver says to open
    assignment       area name -> serving store id (or None)
    raw_link_flags   optional unrepaired link bits, so double-assignment can be
                     detected even though `assignment` keeps only one server
    """
    selected = sorted(set(int(i) for i in selected_stores))
    known_ids = set(instance.store_ids)
    violations: list[str] = []
    checks: list[dict] = []

    # ------------------------------------------------ unknown store ids
    unknown = [i for i in selected if i not in known_ids]
    if unknown:
        violations.append(f"solution selects store ids not in the instance: {unknown}")
        selected = [i for i in selected if i in known_ids]

    # ----------------------------------------------------- money and volume
    opening_cost = sum(instance.store(i).opening_cost for i in selected)
    revenue = 0.0
    delivery_cost = 0.0
    served_units = 0.0
    load: dict[int, float] = {i: 0.0 for i in selected}

    area_rows: list[dict] = []
    for area in instance.areas:
        store_id = assignment.get(area.name)
        row = {
            "area": area.name,
            "store_id": store_id,
            "store_name": instance.store(store_id).name
            if store_id in known_ids
            else None,
            "delivery_time_min": None,
            "served": False,
        }

        if store_id is None:
            area_rows.append(row)
            continue

        if store_id not in known_ids:
            violations.append(
                f"area {area.name!r} assigned to unknown store id {store_id}"
            )
            area_rows.append(row)
            continue

        store = instance.store(store_id)

        # Delivery time comes from the instance's MEASURED travel times -- real
        # routed legs where routing was available (see ingestion/osm_ingestion).
        # Recomputing a straight-line estimate here would validate against
        # different physics than the model was built on, and would wrongly
        # reject assignments that the road network actually supports.
        #
        # This stays independent of the solver: `links` is input data, not
        # solver output. A pair with no link is genuinely out of service range,
        # and the straight-line fallback is only used to report how far out.
        measured = instance.links.get((store_id, area.name))
        if measured is not None:
            minutes = measured
            row["delivery_time_source"] = instance.link_source.get(
                (store_id, area.name), "instance"
            )
        else:
            minutes = delivery_time_min(
                store.latitude, store.longitude, area.latitude, area.longitude
            )
            row["delivery_time_source"] = "straight_line_estimate"
        row["delivery_time_min"] = round(minutes, 3)

        # C5 delivery / service radius
        if minutes > area.delivery_time_limit + EPS:
            violations.append(
                f"C5 delivery: {area.name!r} served from store {store_id} in "
                f"{minutes:.2f} min, limit is {area.delivery_time_limit:.2f} min"
            )
            area_rows.append(row)
            continue

        # C2 store-inventory coupling
        if store_id not in selected:
            violations.append(
                f"C2 coupling: area {area.name!r} is served by store {store_id}, "
                f"which the solution does not open (inventory assigned to a "
                f"non-selected store)"
            )
            area_rows.append(row)
            continue

        row["served"] = True
        revenue += area.revenue
        delivery_cost += instance.delivery_cost.get(
            (store_id, area.name), instance_delivery_fallback(instance, minutes, area)
        )
        served_units += area.quantity
        load[store_id] = load.get(store_id, 0.0) + area.volume
        area_rows.append(row)

    # ----------------------------------------- C1 single sourcing
    if raw_link_flags:
        for area in instance.areas:
            servers = [
                i for (i, a), flag in raw_link_flags.items() if a == area.name and flag
            ]
            if len(servers) > 1:
                violations.append(
                    f"C1 single sourcing: area {area.name!r} is assigned to "
                    f"{len(servers)} stores {sorted(servers)}; at most one is allowed"
                )
    checks.append(
        {
            "name": "C1_single_sourcing",
            "satisfied": not any(v.startswith("C1") for v in violations),
            "limit": 1,
            "used": None,
            "detail": "each area served by at most one store",
        }
    )

    checks.append(
        {
            "name": "C2_store_inventory_coupling",
            "satisfied": not any(v.startswith("C2") for v in violations),
            "limit": None,
            "used": None,
            "detail": "inventory only allocated to opened stores",
        }
    )

    # ----------------------------------------------- C3 capacity
    cap_ok = True
    for store_id in selected:
        cap = instance.store(store_id).storage_capacity
        used = load.get(store_id, 0.0)
        if used > cap + EPS:
            cap_ok = False
            violations.append(
                f"C3 capacity: store {store_id} holds {used:.2f} volume units "
                f"but its capacity is {cap:.2f}"
            )
    storage_used = sum(load.values())
    storage_available = sum(instance.store(i).storage_capacity for i in selected)
    checks.append(
        {
            "name": "C3_storage_capacity",
            "satisfied": cap_ok,
            "limit": round(storage_available, 4),
            "used": round(storage_used, 4),
            "detail": "per-store volume within that store's capacity",
        }
    )

    # ------------------------------------------------- C4 budget
    budget_ok = opening_cost <= instance.budget + EPS
    if not budget_ok:
        violations.append(
            f"C4 budget: opening cost {opening_cost:.2f} exceeds budget "
            f"{instance.budget:.2f}"
        )
    checks.append(
        {
            "name": "C4_budget",
            "satisfied": budget_ok,
            "limit": round(instance.budget, 4),
            "used": round(opening_cost, 4),
            "detail": "total opening cost within budget",
        }
    )

    checks.append(
        {
            "name": "C5_delivery_time",
            "satisfied": not any(v.startswith("C5") for v in violations),
            "limit": None,
            "used": None,
            "detail": "every served area within its delivery time limit",
        }
    )

    # --------------------------------------- demand satisfaction (reported)
    total_units = instance.total_demand_units
    service_level = safe_div(served_units, total_units)
    checks.append(
        {
            "name": "demand_satisfaction",
            # Not a hard constraint: the model may leave an area unserved if
            # serving it costs more than its margin. Reported, never failed.
            "satisfied": True,
            "limit": round(total_units, 4),
            "used": round(served_units, 4),
            "detail": f"{100 * service_level:.2f}% of demand units served "
            f"(leaving demand unserved is permitted by design)",
        }
    )

    # ------------------------------------------- inventory allocation
    product_by_id = {p.id: p for p in instance.products}
    inv: dict[tuple[int, int], float] = {}
    for area in instance.areas:
        store_id = assignment.get(area.name)
        if store_id is None or store_id not in selected:
            continue
        if not any(r["area"] == area.name and r["served"] for r in area_rows):
            continue
        for pid, qty in area.demand_by_product.items():
            inv[(store_id, pid)] = inv.get((store_id, pid), 0.0) + qty

    inventory_rows = [
        {
            "store_id": sid,
            "store_name": instance.store(sid).name,
            "product_id": pid,
            "product_name": product_by_id[pid].name,
            "quantity": round(qty, 4),
        }
        for (sid, pid), qty in sorted(inv.items())
    ]

    objective = revenue - opening_cost - delivery_cost

    return SolutionMetrics(
        objective_value=objective,
        revenue_captured=revenue,
        opening_cost=opening_cost,
        delivery_cost=delivery_cost,
        demand_units_total=total_units,
        demand_units_served=served_units,
        service_level=service_level,
        budget_used=opening_cost,
        storage_used=storage_used,
        storage_available=storage_available,
        storage_utilization=safe_div(storage_used, storage_available),
        selected_stores=selected,
        selected_store_names=[instance.store(i).name for i in selected],
        area_assignments=area_rows,
        inventory_allocation=inventory_rows,
        feasible=not violations,
        checks=checks,
        violations=violations,
    )


def instance_delivery_fallback(instance, minutes: float, area) -> float:
    """Rider cost for a link the instance did not precompute.

    Only reachable when a solver proposes a link outside the service-feasible
    set. Such a link is already flagged as a C5 violation; this just makes sure
    its cost is still counted instead of silently coming out as zero.
    """
    from app.config import settings

    return settings.rider_cost_per_min * minutes * area.orders
