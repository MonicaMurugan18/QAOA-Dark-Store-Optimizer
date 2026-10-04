"""Product request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=80)

    # gt=0, not ge=0: a product occupying zero space would let a store hold an
    # unlimited number of them and make the capacity constraint meaningless.
    unit_volume: float = Field(gt=0, description="Volume units consumed by one unit")
    unit_cost: float = Field(ge=0, description="Supplier cost per unit (INR)")

    data_source: str = Field(default="DEMO_ASSUMPTION", max_length=60)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    unit_volume: float | None = Field(default=None, gt=0)
    unit_cost: float | None = Field(default=None, ge=0)
    data_source: str | None = Field(default=None, max_length=60)


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
