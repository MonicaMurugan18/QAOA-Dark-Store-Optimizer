"""Demand request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DemandBase(BaseModel):
    area: str = Field(min_length=1, max_length=120)
    product_id: int = Field(gt=0)

    # ge=0 rejects negative demand at the API boundary.
    demand_quantity: float = Field(ge=0, description="Units demanded per period")

    # gt=0: a limit of zero would make every store unable to serve the area,
    # which is an input error rather than a meaningful instance.
    delivery_time_limit: float = Field(
        gt=0, description="Service promise for this area, in minutes"
    )

    data_source: str = Field(default="DEMO_ASSUMPTION", max_length=60)


class DemandCreate(DemandBase):
    pass


class DemandUpdate(BaseModel):
    area: str | None = Field(default=None, min_length=1, max_length=120)
    product_id: int | None = Field(default=None, gt=0)
    demand_quantity: float | None = Field(default=None, ge=0)
    delivery_time_limit: float | None = Field(default=None, gt=0)
    data_source: str | None = Field(default=None, max_length=60)


class DemandRead(DemandBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class DemandBulkCreate(BaseModel):
    """Bulk insert. Validated as a whole so one bad row rejects the batch."""

    items: list[DemandCreate] = Field(min_length=1, max_length=5000)


class DemandBulkResult(BaseModel):
    created: int
    updated: int
    skipped: int
    detail: list[str] = []
