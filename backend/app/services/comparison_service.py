"""Orchestration and comparison.

This module is the only place that knows how to run an optimization end to end:
build the instance, call the solvers, persist the run, and compare results. The
routers call into here so no optimization logic lives in the HTTP layer.

It does NOT reimplement any solver. It calls data_service, qaoa_service,
classical_service and validation_service exactly as they are.

ON OPTIMALITY GAPS
==================
A gap is only meaningful against a reference that is actually optimal. We
therefore publish a gap ONLY when a solver reported a proven optimum for this
instance -- in practice, PuLP/CBC returning status "Optimal". If CBC hit its
time limit, its value is just the best found so far, no reference exists, and
`optimality_gap_percent` stays None rather than being quietly computed against a
number that has no guarantee behind it.

The word "accuracy" is deliberately not used anywhere: these are optimisation
objective values, not predictions.
"""

from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.models import Method, OptimizationResult, OptimizationRun, RunStatus
from app.schemas.optimization import RunRequest
from app.services import classical_service, qaoa_service
from app.services.data_service import InstanceError, build_instance
from app.services.qaoa_service import QaoaTooLargeError
from app.utils.helpers import safe_div

QAOA_SOLVER = "qaoa"
CLASSICAL_SOLVER = "classical"


class SolverFailure(RuntimeError):
    """A solver raised. Carries the solver name so the API can say which."""

    def __init__(self, solver: str, message: str):
        self.solver = solver
        super().__init__(message)


# ===========================================================================
# Running
# ===========================================================================
def execute_run(db: Session, req: RunRequest) -> OptimizationRun:
    """Build the instance, run the requested solver(s), persist everything.

    Always returns a persisted OptimizationRun. If every solver failed, the run
    is saved with status FAILED and the reason recorded -- never a fake success.
    """
    instance = build_instance(
        db,
        budget=req.budget,
        default_delivery_limit=req.delivery_time_limit,
        store_ids=req.store_ids,
        product_ids=req.product_ids,
        areas=req.areas,
    )

    run = OptimizationRun(
        budget=req.budget,
        delivery_time_limit=req.delivery_time_limit,
        method=req.method,
        status=RunStatus.RUNNING.value,
        parameters={
            "requested": req.model_dump(mode="json"),
            "instance": instance.size_summary(),
            "instance_warnings": instance.warnings,
            "constraint_rounding": instance.rounding_report(),
        },
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    wanted: list[str] = []
    if req.method in (Method.QAOA.value, Method.BOTH.value):
        wanted.append(QAOA_SOLVER)
    if req.method in (Method.CLASSICAL.value, Method.BOTH.value):
        wanted.append(CLASSICAL_SOLVER)

    errors: dict[str, str] = {}
    succeeded = 0

    for solver in wanted:
        try:
            if solver == QAOA_SOLVER:
                metrics, details = qaoa_service.solve_qaoa(
                    instance,
                    reps=req.options.reps,
                    maxiter=req.options.maxiter,
                    shots=req.options.shots,
                    seed=req.options.seed,
                )
            else:
                metrics, details = classical_service.solve_classical(
                    instance, time_limit_sec=req.options.time_limit_sec
                )
        except QaoaTooLargeError as exc:
            errors[solver] = f"instance too large for the simulator: {exc}"
            continue
        except Exception as exc:  # noqa: BLE001 - surfaced, never swallowed
            errors[solver] = f"{type(exc).__name__}: {exc}"
            continue

        payload = metrics.as_result_payload()
        db.add(
            OptimizationResult(
                optimization_run_id=run.id,
                solver=solver,
                objective_value=payload["objective_value"],
                customers_served=payload["customers_served"],
                budget_used=payload["budget_used"],
                storage_used=payload["storage_used"],
                runtime=float(details.get("runtime", 0.0)),
                selected_stores=payload["selected_stores"],
                inventory_allocation=payload["inventory_allocation"],
                validation=payload["validation"],
                solver_details={
                    **details,
                    "demand_units_total": payload["demand_units_total"],
                    "demand_units_served": payload["demand_units_served"],
                    "service_level": payload["service_level"],
                    "storage_available": payload["storage_available"],
                    "storage_utilization": payload["storage_utilization"],
                    "budget_limit": instance.budget,
                    "selected_store_names": payload["selected_store_names"],
                    "area_assignments": payload["area_assignments"],
                },
            )
        )
        succeeded += 1

    run.status = (
        RunStatus.COMPLETED.value if succeeded else RunStatus.FAILED.value
    )
    if errors:
        run.error_message = "; ".join(f"{k}: {v}" for k, v in errors.items())[:1000]
        run.parameters = {**(run.parameters or {}), "solver_errors": errors}
    db.commit()
    db.refresh(run)

    if not succeeded:
        raise SolverFailure(
            ",".join(wanted), run.error_message or "all solvers failed"
        )
    return run


# ===========================================================================
# Serialising a stored result
# ===========================================================================
def result_to_payload(row: OptimizationResult) -> dict:
    """Flatten a persisted result into the API's SolverResult shape."""
    d = row.solver_details or {}
    return {
        "solver": row.solver,
        "objective_value": row.objective_value,
        "customers_served": row.customers_served,
        "demand_units_total": d.get("demand_units_total", 0.0),
        "demand_units_served": d.get("demand_units_served", row.customers_served),
        "service_level": d.get("service_level", 0.0),
        "budget_used": row.budget_used,
        "budget_limit": d.get("budget_limit", 0.0),
        "storage_used": row.storage_used,
        "storage_available": d.get("storage_available", 0.0),
        "storage_utilization": d.get("storage_utilization", 0.0),
        "runtime": row.runtime,
        "selected_stores": row.selected_stores or [],
        "selected_store_names": d.get("selected_store_names", []),
        "area_assignments": d.get("area_assignments", []),
        "inventory_allocation": row.inventory_allocation or [],
        "validation": row.validation
        or {"feasible": False, "checks": [], "violations": ["no validation recorded"]},
        "solver_details": {
            k: v
            for k, v in d.items()
            if k
            not in {
                "demand_units_total",
                "demand_units_served",
                "service_level",
                "storage_available",
                "storage_utilization",
                "budget_limit",
                "selected_store_names",
                "area_assignments",
            }
        },
    }


def run_to_detail(run: OptimizationRun) -> dict:
    return {
        "id": run.id,
        "created_at": run.created_at,
        "budget": run.budget,
        "delivery_time_limit": run.delivery_time_limit,
        "method": run.method,
        "status": run.status,
        "parameters": run.parameters,
        "error_message": run.error_message,
        "results": [result_to_payload(r) for r in run.results],
    }


# ===========================================================================
# Comparison
# ===========================================================================
def _flat(row: OptimizationResult) -> dict:
    """The compact per-solver block the spec asks for."""
    d = row.solver_details or {}
    val = row.validation or {}
    return {
        "objective_value": row.objective_value,
        "customers_served": row.customers_served,
        "budget_used": row.budget_used,
        "runtime": row.runtime,
        "storage_used": row.storage_used,
        "storage_utilization": d.get("storage_utilization"),
        "service_level": d.get("service_level"),
        "selected_stores": row.selected_stores or [],
        "feasible": val.get("feasible"),
        "constraint_violations": val.get("violations", []),
    }


def _metric(name: str, q, c, higher_is_better: bool) -> dict:
    """One comparison row. `better` is None when either side is missing."""
    out = {"metric": name, "qaoa": q, "classical": c, "difference": None,
           "better": None}
    if q is None or c is None:
        return out
    out["difference"] = round(q - c, 6)
    if abs(q - c) < 1e-9:
        out["better"] = "tie"
    elif (q > c) == higher_is_better:
        out["better"] = "qaoa"
    else:
        out["better"] = "classical"
    return out


def build_comparison(run: OptimizationRun) -> dict:
    """Compare the solvers on this run. Reports only what was actually produced."""
    by_solver = {r.solver: r for r in run.results}
    q = by_solver.get(QAOA_SOLVER)
    c = by_solver.get(CLASSICAL_SOLVER)

    notes: list[str] = []
    if q is None:
        notes.append("No QAOA result stored for this run.")
    if c is None:
        notes.append("No classical result stored for this run.")
    if run.error_message:
        notes.append(f"Solver errors on this run: {run.error_message}")

    qf = _flat(q) if q else None
    cf = _flat(c) if c else None

    def pick(row, key):
        return None if row is None else row.get(key)

    metrics = [
        _metric("objective_value", pick(qf, "objective_value"),
                pick(cf, "objective_value"), higher_is_better=True),
        _metric("customers_served", pick(qf, "customers_served"),
                pick(cf, "customers_served"), higher_is_better=True),
        _metric("service_level", pick(qf, "service_level"),
                pick(cf, "service_level"), higher_is_better=True),
        _metric("budget_used", pick(qf, "budget_used"),
                pick(cf, "budget_used"), higher_is_better=False),
        _metric("storage_utilization", pick(qf, "storage_utilization"),
                pick(cf, "storage_utilization"), higher_is_better=True),
        _metric("runtime", pick(qf, "runtime"), pick(cf, "runtime"),
                higher_is_better=False),
        _metric(
            "constraint_violations",
            None if qf is None else float(len(qf["constraint_violations"])),
            None if cf is None else float(len(cf["constraint_violations"])),
            higher_is_better=False,
        ),
    ]

    # ------------------------------------------------- optimality gap
    # Only against a PROVEN optimum. See the module docstring.
    reference_solver = None
    reference_objective = None
    gaps: dict[str, float] | None = None

    for row in (c, q):
        if row is None:
            continue
        details = row.solver_details or {}
        validation = row.validation or {}
        if details.get("proven_optimal") and validation.get("feasible"):
            reference_solver = row.solver
            reference_objective = row.objective_value
            break

    if reference_solver is not None and reference_objective not in (None, 0):
        gaps = {}
        for row in (q, c):
            if row is None:
                continue
            # Maximisation: a positive gap means this solver came in BELOW the
            # proven optimum by that percentage.
            gaps[row.solver] = round(
                100.0
                * safe_div(reference_objective - row.objective_value,
                           abs(reference_objective)),
                6,
            )
        notes.append(
            f"Optimality gap is measured against {reference_solver!r}, which "
            f"reported a PROVEN optimum for this instance. A positive gap means "
            f"the solver fell short of that optimum."
        )
    else:
        notes.append(
            "No optimality gap reported: no solver on this run provided a proven "
            "optimum, so there is no valid reference to measure against."
        )

    notes.append(
        "QAOA is a sampling heuristic with no optimality guarantee; a lower "
        "objective than the classical baseline is an expected outcome, not an "
        "error. Solution quality depends on circuit depth (reps), shots and "
        "optimizer iterations."
    )

    return {
        "run_id": run.id,
        "qaoa": qf,
        "classical": cf,
        "metrics": metrics,
        "reference_solver": reference_solver,
        "reference_objective": reference_objective,
        "optimality_gap_percent": gaps,
        "notes": notes,
    }
