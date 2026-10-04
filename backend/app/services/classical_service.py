"""Classical Operations Research baseline, using PuLP + CBC.

Flow:  instance -> MILP model -> PuLP/CBC -> solution -> decode -> validate

SAME PROBLEM, DIFFERENT ENCODING
================================
This solves exactly the model stated in data_service: the same variables, the
same objective, the same constraints C1-C5, on the same instance. The only
difference from the QAOA path is how constraints are expressed:

    PuLP  keeps C1-C4 as HARD linear constraints. CBC will not return a point
          that breaks them.
    QUBO  folds them into the objective as PENALTIES, because a QAOA circuit
          cannot represent a hard constraint.

Both describe the same feasible set. Both solutions are then checked by the same
independent validator, which trusts neither solver's own verdict.

The capacity and budget constraints use the integerised coefficients from
OptimizationInstance, exactly as the QUBO does. Using exact floats here and
rounded values there would silently make this a slightly different problem and
the comparison would not be fair.

ON OPTIMALITY
=============
CBC is an exact branch-and-bound MILP solver. When it reports status "Optimal"
it has PROVEN optimality for this model, and `proven_optimal` is set to True.
If it hits the time limit it returns the best solution found so far and
`proven_optimal` is False -- in that case the value is a bound, not the optimum,
and nothing downstream may treat it as a reference.
"""

from __future__ import annotations

import time

import pulp

from app.services.data_service import OptimizationInstance
from app.services.validation_service import SolutionMetrics, evaluate_solution

SOLVER_NAME = "classical_pulp_cbc"


def solve_classical(
    instance: OptimizationInstance, time_limit_sec: int = 60
) -> tuple[SolutionMetrics, dict]:
    """Solve the MILP. Returns (metrics, solver_details)."""
    started = time.perf_counter()

    prob = pulp.LpProblem("joint_darkstore_location_inventory", pulp.LpMaximize)

    # ---------------------------------------------------------- variables
    # x_i: open store i
    x = {
        s.id: pulp.LpVariable(f"x_{s.id}", cat=pulp.LpBinary) for s in instance.stores
    }
    # s_{i,a}: store i serves area a. Only service-feasible links exist, which
    # is how C5 (delivery time) is enforced -- structurally, not as a constraint.
    y = {
        (i, a): pulp.LpVariable(f"s_{i}__{a.replace(' ', '_')}", cat=pulp.LpBinary)
        for (i, a) in sorted(instance.links)
    }

    # ---------------------------------------------------------- objective
    # maximise  served margin - opening cost - rider cost
    prob += (
        pulp.lpSum(
            (instance.area(a).revenue - instance.delivery_cost[(i, a)]) * y[(i, a)]
            for (i, a) in y
        )
        - pulp.lpSum(instance.store(i).opening_cost * x[i] for i in x)
    ), "net_margin"

    # ------------------------------------------------ C1 single sourcing
    for area in instance.areas:
        servers = instance.servers_of(area.name)
        if servers:
            prob += (
                pulp.lpSum(y[(i, area.name)] for i in servers) <= 1,
                f"c1_single_source_{area.name.replace(' ', '_')}",
            )

    # ------------------------------------------------------ C2 coupling
    # Inventory (represented by the assignment) may only go to an opened store.
    for (i, a) in y:
        prob += (y[(i, a)] <= x[i], f"c2_coupling_{i}_{a.replace(' ', '_')}")

    # ------------------------------------------------------ C3 capacity
    vol_int = instance.area_volume_int
    cap_int = instance.store_capacity_int
    for s in instance.stores:
        served = instance.served_by(s.id)
        if served:
            prob += (
                pulp.lpSum(vol_int[a] * y[(s.id, a)] for a in served)
                <= cap_int[s.id] * x[s.id],
                f"c3_capacity_{s.id}",
            )

    # -------------------------------------------------------- C4 budget
    cost_int = instance.store_cost_int
    prob += (
        pulp.lpSum(cost_int[i] * x[i] for i in x) <= instance.budget_int,
        "c4_budget",
    )

    # ------------------------------------------------------------- solve
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit_sec)
    status_code = prob.solve(solver)
    runtime = time.perf_counter() - started

    status = pulp.LpStatus[status_code]
    proven_optimal = status == "Optimal"

    # ------------------------------------------------------------ decode
    selected: list[int] = []
    assignment: dict[str, int | None] = {a.name: None for a in instance.areas}
    raw_flags: dict[tuple[int, str], int] = {}

    if status in {"Optimal", "Not Solved", "Undefined"}:
        for i, var in x.items():
            if var.value() is not None and round(var.value()) == 1:
                selected.append(i)
        for (i, a), var in y.items():
            flag = 1 if var.value() is not None and round(var.value()) == 1 else 0
            raw_flags[(i, a)] = flag
            if flag:
                assignment[a] = i

    metrics = evaluate_solution(instance, selected, assignment, raw_flags)

    details = {
        "solver": "PuLP + CBC (branch and bound)",
        "pulp_status": status,
        "proven_optimal": proven_optimal,
        "n_variables": len(x) + len(y),
        "n_constraints": len(prob.constraints),
        "time_limit_sec": time_limit_sec,
        "pulp_objective_value": (
            float(pulp.value(prob.objective))
            if pulp.value(prob.objective) is not None
            else None
        ),
        "integerised_constraints": True,
        "notes": [
            "CBC is an exact MILP solver; status 'Optimal' means optimality was "
            "proven FOR THIS MODEL, not for any reformulation of it.",
        ],
    }
    if not proven_optimal:
        details["notes"].append(
            f"status is {status!r}, so this value is the best found within the "
            f"time limit and must not be used as an optimality reference."
        )

    return metrics, {**details, "runtime": runtime}
