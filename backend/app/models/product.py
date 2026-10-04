"""Product / SKU catalogue."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)

    # Shelf/bin space one unit consumes. This is the currency that
    # Store.storage_capacity is measured in, which is how a single capacity
    # number can bound a basket of differently sized products.
    unit_volume: Mapped[float] = mapped_column(Float, nullable=False)

    # What we pay a supplier per unit. Demand VALUE is unit_cost * quantity;
    # the reward for serving it is that value times settings.gross_margin.
    unit_cost: Mapped[float] = mapped_column(Float, nullable=False)

    data_source: Mapped[str] = mapped_column(
        String(60), nullable=False, default="DEMO_ASSUMPTION",
        server_default="DEMO_ASSUMPTION",
    )

    # ------------------------------------------------------------------
    # Catalogue provenance. A real platform catalogue gives name, brand,
    # category, pack size and MRP. It does NOT give supplier cost or the shelf
    # volume the optimizer needs, so those are derived and labelled separately.
    # ------------------------------------------------------------------
    external_id: Mapped[str | None] = mapped_column(
        String(80), nullable=True, index=True, unique=True
    )
    platform: Mapped[str | None] = mapped_column(String(60), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pack_quantity: Mapped[str | None] = mapped_column(String(60), nullable=True)
    mrp_inr: Mapped[float | None] = mapped_column(Float, nullable=True)

    catalogue_source_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="synthetic", server_default="synthetic"
    )
    source_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_date: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # unit_volume is DERIVED from pack_quantity by a documented rule, and
    # unit_cost is DERIVED from MRP. Neither is observed, so both are labelled.
    volume_source_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="synthetic", server_default="synthetic"
    )
    cost_source_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="synthetic", server_default="synthetic"
    )

    demands: Mapped[list["Demand"]] = relationship(  # noqa: F821
        back_populates="product", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("unit_volume > 0", name="ck_product_volume_pos"),
        CheckConstraint("unit_cost >= 0", name="ck_product_cost_nonneg"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Product id={self.id} name={self.name!r}>"
