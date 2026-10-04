"""Store request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StoreBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    area: str = Field(min_length=1, max_length=120)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    # ge=0 is what rejects negative costs and capacities at the API boundary,
    # before anything reaches the database.
    opening_cost: float = Field(ge=0, description="Cost per planning period (INR/day)")
    storage_capacity: float = Field(ge=0, description="Capacity in volume units")

    platform: str | None = Field(default=None, max_length=80)
    is_candidate: bool = True
    data_source: str = Field(
        default="DEMO_ASSUMPTION",
        max_length=60,
        description="Provenance of this row's numbers, e.g. REAL_SURVEY, "
        "APPROX_AREA_CENTROID, DEMO_ASSUMPTION",
    )


class StoreCreate(StoreBase):
    pass


class StoreUpdate(BaseModel):
    """Every field optional: PUT applies only what is supplied."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    area: str | None = Field(default=None, min_length=1, max_length=120)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    opening_cost: float | None = Field(default=None, ge=0)
    storage_capacity: float | None = Field(default=None, ge=0)
    platform: str | None = Field(default=None, max_length=80)
    is_candidate: bool | None = None
    data_source: str | None = Field(default=None, max_length=60)


class StoreRead(StoreBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
