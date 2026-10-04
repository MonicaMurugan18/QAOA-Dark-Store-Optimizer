"""Candidate dark-store locations."""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    area: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    # Cost of opening/operating this store for one planning period (one day).
    # Includes rent, staff, utilities and amortised fit-out; see README.
    opening_cost: Mapped[float] = mapped_column(Float, nullable=False)

    # Storage capacity in VOLUME units, matching Product.unit_volume, so a
    # mixed basket can be bounded by a single number.
    storage_capacity: Mapped[float] = mapped_column(Float, nullable=False)

    platform: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # Only candidates take part in the optimization. Already-open stores can be
    # kept in the table for reference with is_candidate = False.
    is_candidate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )

    # Provenance. Real surveyed values vs demo assumptions must never be
    # confused, so every row says where its numbers came from.
    data_source: Mapped[str] = mapped_column(
        String(60), nullable=False, default="DEMO_ASSUMPTION",
        server_default="DEMO_ASSUMPTION",
    )

    # ------------------------------------------------------------------
    # PER-FIELD-GROUP PROVENANCE
    #
    # A store's LOCATION can be real public data (OpenStreetMap) while its
    # OPENING COST and CAPACITY are prototype assumptions. Recording one
    # source_type for the whole row would blur that, so the three are tracked
    # separately and the API reports each one.
    # ------------------------------------------------------------------
    external_id: Mapped[str | None] = mapped_column(
        String(80), nullable=True, index=True, unique=True
    )

    # location: where name / lat / lon / area came from
    location_source_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="synthetic", server_default="synthetic"
    )
    source_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    verified_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    active_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown", server_default="unknown"
    )

    # cost and capacity: almost always synthetic until operator data arrives
    cost_source_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="synthetic", server_default="synthetic"
    )
    capacity_source_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="synthetic", server_default="synthetic"
    )

    __table_args__ = (
        CheckConstraint("opening_cost >= 0", name="ck_store_opening_cost_nonneg"),
        CheckConstraint("storage_capacity >= 0", name="ck_store_capacity_nonneg"),
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="ck_store_lat"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="ck_store_lon"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Store id={self.id} name={self.name!r} area={self.area!r}>"
