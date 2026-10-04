"""Optimization request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------- request
class SolverOptions(BaseModel):
    """Solver knobs. Both solvers receive the same instance regardless."""

    # QAOA
    reps: int = Field(default=3, ge=1, le=12, description="QAOA depth p")

    # ge=1, not ge=10: very small iteration counts are deliberately allowed so a
    # run can be smoke-tested cheaply before committing to a full optimisation.
    # Low budgets return feasible but suboptimal plans -- that is reported in
    # solver_details, not prevented.
    maxiter: int = Field(
        default=200,
        ge=1,
        le=5000,
        description="Classical optimizer iterations. Very low values finish in "
        "milliseconds but typically return a suboptimal plan.",
    )
    shots: int = Field(default=2048, ge=32, le=100_000)
    seed: int = Field(default=42, ge=0)

    # Classical (PuLP / CBC)
    time_limit_sec: int = Field(default=60, ge=1, le=3600)


class OptimizationRequest(BaseModel):
    # ge=0 rejects a negative budget.
    budget: float = Field(ge=0, description="Total opening-cost spend allowed")

    delivery_time_limit: float = Field(
        default=15.0,
        gt=0,
        description="Fallback service promise in minutes; an area's own "
        "delivery_time_limit takes precedence when present",
    )

    # Restrict the instance. Empty/None means "use everything in the database".
    store_ids: list[int] | None = Field(default=None, description="Candidate subset")
    product_ids: list[int] | None = None
    areas: list[str] | None = None

    options: SolverOptions = Field(default_factory=SolverOptions)


class RunRequest(OptimizationRequest):
    method: Literal["qaoa", "classical", "both"] = "both"


# -------------------------------------------------------------------- response
class InventoryAllocationItem(BaseModel):
    store_id: int
    store_name: str
    product_id: int
    product_name: str
    quantity: float


class AreaAssignmentItem(BaseModel):
    area: str
    store_id: int | None
    store_name: str | None
    delivery_time_min: float | None
    served: bool


class ConstraintCheck(BaseModel):
    name: str
    satisfied: bool
    limit: float | None = None
    used: float | None = None
    detail: str | None = None


class ValidationReport(BaseModel):
    """Independent re-check of a solution against the raw instance data."""

    feasible: bool
    checks: list[ConstraintCheck]
    violations: list[str]


class SolverResult(BaseModel):
    solver: str
    objective_value: float
    customers_served: float
    demand_units_total: float
    demand_units_served: float
    service_level: float = Field(description="served / total demand units, 0..1")
    budget_used: float
    budget_limit: float
    storage_used: float
    storage_available: float
    storage_utilization: float
    runtime: float
    selected_stores: list[int]
    selected_store_names: list[str]
    area_assignments: list[AreaAssignmentItem]
    inventory_allocation: list[InventoryAllocationItem]
    validation: ValidationReport
    solver_details: dict = {}


class ComparisonMetric(BaseModel):
    metric: str
    qaoa: float | None = None
    classical: float | None = None
    difference: float | None = None
    better: str | None = Field(
        default=None, description="'qaoa', 'classical', 'tie', or None"
    )


class ComparisonResponse(BaseModel):
    run_id: int

    # Flat shape requested in the spec, kept verbatim for API compatibility.
    qaoa: dict | None = None
    classical: dict | None = None

    metrics: list[ComparisonMetric] = []

    # Only populated when a solver provided a proven optimality guarantee for
    # this instance. Otherwise None -- we do not assume a reference is optimal.
    reference_solver: str | None = None
    reference_objective: float | None = None
    optimality_gap_percent: dict[str, float] | None = None

    notes: list[str] = []


class OptimizationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    budget: float
    delivery_time_limit: float
    method: str
    status: str
    parameters: dict | None = None
    error_message: str | None = None


class OptimizationRunDetail(OptimizationRunRead):
    results: list[SolverResult] = []
