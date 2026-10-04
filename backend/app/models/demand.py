"""Demand per customer area, per product."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Demand(Base):
    __tablename__ = "demand"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Customer area name. Kept as a string (not a foreign key) because areas are
    # demand clusters, not entities we manage; a store's `area` uses the same
    # vocabulary so the two can be matched.
    area: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )

    demand_quantity: Mapped[float] = mapped_column(Float, nullable=False)

    # Service promise for this area, in minutes. A store may only serve an area
    # if its delivery time is within this limit -- the delivery constraint.
    delivery_time_limit: Mapped[float] = mapped_column(Float, nullable=False)

    data_source: Mapped[str] = mapped_column(
        String(60), nullable=False, default="DEMO_ASSUMPTION",
        server_default="DEMO_ASSUMPTION",
    )

    product: Mapped["Product"] = relationship(back_populates="demands")  # noqa: F821

    __table_args__ = (
        UniqueConstraint("area", "product_id", name="uq_demand_area_product"),
        CheckConstraint("demand_quantity >= 0", name="ck_demand_qty_nonneg"),
        CheckConstraint("delivery_time_limit > 0", name="ck_demand_tlimit_pos"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Demand area={self.area!r} product_id={self.product_id}>"
