"""Optimization endpoints.

These routers contain NO optimization logic. They validate input, delegate to
comparison_service (which calls data_service / qubo_service / qaoa_service /
classical_service / validation_service), and shape the response.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import OptimizationRun
from app.schemas.optimization import (
    ComparisonResponse,
    OptimizationRequest,
    OptimizationRunRead,
    RunRequest,
)
from app.services import comparison_service
from app.services.data_service import InstanceError, build_instance, distance_report
from app.services.data_service import suggest_instance as _suggest_instance
from app.services.qaoa_service import qubo_only

router = APIRouter(prefix="/api/optimization", tags=["optimization"])


def _execute(db: Session, req: RunRequest) -> dict:
    """Shared path for /run, /qaoa and /classical."""
    try:
        run = comparison_service.execute_run(db, req)
    except InstanceError as exc:
        # The instance itself is unusable: bad ids, no reachable store, budget
        # below the cheapest store. That is a request problem, not a server bug.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"cannot build an optimization instance: {exc}",
        ) from exc
    except comparison_service.SolverFailure as exc:
        # Every requested solver failed. Report which, and why, with the run id
        # so the failure is inspectable instead of invisible.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "all requested solvers failed; no result was produced",
                "solvers": exc.solver,
                "error": str(exc),
            },
        ) from exc

    return comparison_service.run_to_detail(run)


@router.post(
    "/run",
    summary="Run QAOA and/or the classical solver",
    description=(
        "Builds the optimization instance from the database and runs the "
        "requested method. `method=both` (default) runs QAOA and PuLP/CBC on "
        "the identical instance so they can be compared."
    ),
)
def run_optimization(req: RunRequest, db: Session = Depends(get_db)) -> dict:
    return _execute(db, req)


@router.post(
    "/qaoa",
    summary="Run QAOA only",
    description=(
        "QAOA on a local statevector simulator. It samples a biased "
        "distribution and carries NO optimality guarantee; solution quality "
        "depends on `reps` (circuit depth), `shots` and `maxiter`. Low depth "
        "can return a feasible but suboptimal plan."
    ),
)
def run_qaoa(req: OptimizationRequest, db: Session = Depends(get_db)) -> dict:
    return _execute(db, RunRequest(**req.model_dump(), method="qaoa"))


@router.post(
    "/classical",
    summary="Run the classical OR baseline only",
    description=(
        "PuLP + CBC branch and bound on the same model. When CBC reports "
        "status 'Optimal' the result is a PROVEN optimum for this instance and "
        "becomes the reference for optimality gaps."
    ),
)
def run_classical(req: OptimizationRequest, db: Session = Depends(get_db)) -> dict:
    return _execute(db, RunRequest(**req.model_dump(), method="classical"))


@router.post(
    "/preview",
    summary="Size an instance without solving it",
    description=(
        "Builds the instance and the QUBO and reports qubit count, variables "
        "and service-feasible links. Use this to check an instance fits the "
        "simulator before paying for a QAOA run."
    ),
)
def preview_instance(req: OptimizationRequest, db: Session = Depends(get_db)) -> dict:
    try:
        instance = build_instance(
            db,
            budget=req.budget,
            default_delivery_limit=req.delivery_time_limit,
            store_ids=req.store_ids,
            product_ids=req.product_ids,
            areas=req.areas,
        )
    except InstanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"cannot build an optimization instance: {exc}",
        ) from exc

    return {
        "instance": instance.size_summary(),
        "warnings": instance.warnings,
        "constraint_rounding": instance.rounding_report(),
        "qubo_compact": qubo_only(instance, encoding="compact"),
        "store_area_links": distance_report(instance),
    }


@router.get(
    "/suggest-instance",
    summary="Propose a solver-sized instance from the live data",
    description=(
        "Picks demand zones that actually have demand and are reachable within "
        "the delivery limit by a routed leg, plus the stores that serve them, "
        "small enough to stay inside the simulator's qubit budget. Nothing is "
        "hardcoded: the selection is a query over the ingested data."
    ),
)
def suggest_instance(
    db: Session = Depends(get_db),
    delivery_time_limit: float = Query(default=15.0, gt=0),
    max_stores: int = Query(default=4, ge=1, le=12),
    max_zones: int = Query(default=4, ge=1, le=12),
) -> dict:
    try:
        return _suggest_instance(
            db,
            delivery_limit=delivery_time_limit,
            max_stores=max_stores,
            max_zones=max_zones,
        )
    except InstanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.get(
    "/runs",
    response_model=list[OptimizationRunRead],
    summary="List optimization runs",
)
def list_runs(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[OptimizationRun]:
    stmt = select(OptimizationRun).order_by(OptimizationRun.id.desc())
    return list(db.execute(stmt.offset(offset).limit(limit)).scalars())


def _run_or_404(db: Session, run_id: int) -> OptimizationRun:
    run = db.get(OptimizationRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"optimization run {run_id} does not exist",
        )
    return run


@router.get(
    "/{run_id}",
    summary="Get a stored run with every solver result",
)
def get_run(run_id: int, db: Session = Depends(get_db)) -> dict:
    return comparison_service.run_to_detail(_run_or_404(db, run_id))


@router.get(
    "/{run_id}/comparison",
    response_model=ComparisonResponse,
    summary="Compare QAOA against the classical baseline for a run",
    description=(
        "Compares objective value, demand served, budget used, storage "
        "utilization, constraint violations and runtime. An optimality gap is "
        "reported ONLY when a solver on this run provided a proven optimum."
    ),
)
def get_comparison(run_id: int, db: Session = Depends(get_db)) -> dict:
    run = _run_or_404(db, run_id)
    if not run.results:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"run {run_id} has no stored results to compare",
                "status": run.status,
                "error": run.error_message,
            },
        )
    return comparison_service.build_comparison(run)
