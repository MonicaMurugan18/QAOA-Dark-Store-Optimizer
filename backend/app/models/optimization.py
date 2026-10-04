"""Optimization runs and their per-solver results."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base


class RunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Method(str, enum.Enum):
    QAOA = "qaoa"
    CLASSICAL = "classical"
    BOTH = "both"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OptimizationRun(Base):
    __tablename__ = "optimization_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    # Total spend allowed on opening costs for one planning period.
    budget: Mapped[float] = mapped_column(Float, nullable=False)

    # Global fallback service promise; an area's own limit wins if it has one.
    delivery_time_limit: Mapped[float] = mapped_column(Float, nullable=False)

    method: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RunStatus.PENDING.value
    )

    # Free-form record of the instance and solver options actually used, so a
    # run can be reproduced and audited later.
    parameters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    results: Mapped[list["OptimizationResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("budget >= 0", name="ck_run_budget_nonneg"),
        CheckConstraint("delivery_time_limit > 0", name="ck_run_tlimit_pos"),
    )


class OptimizationResult(Base):
    __tablename__ = "optimization_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    optimization_run_id: Mapped[int] = mapped_column(
        ForeignKey("optimization_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    solver: Mapped[str] = mapped_column(String(40), nullable=False)

    # Objective value in the MAXIMISATION sense used throughout the project:
    #   served demand margin - opening cost - delivery cost
    objective_value: Mapped[float] = mapped_column(Float, nullable=False)

    # Units of demand actually served. Named "customers_served" to match the API
    # contract; it is a demand-unit count, not a headcount of people.
    customers_served: Mapped[float] = mapped_column(Float, nullable=False)

    budget_used: Mapped[float] = mapped_column(Float, nullable=False)
    storage_used: Mapped[float] = mapped_column(Float, nullable=False)
    runtime: Mapped[float] = mapped_column(Float, nullable=False)

    selected_stores: Mapped[list | None] = mapped_column(JSON, nullable=True)
    inventory_allocation: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Independent post-hoc validation of this solution against the raw data.
    validation: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Extra solver-specific detail: qubit count, reps, PuLP status, and so on.
    solver_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    run: Mapped[OptimizationRun] = relationship(back_populates="results")

    __table_args__ = (
        CheckConstraint("runtime >= 0", name="ck_result_runtime_nonneg"),
        CheckConstraint("budget_used >= 0", name="ck_result_budget_nonneg"),
    )
