"""Demand zones and store→zone travel times.

DemandZone replaces the free-text `area` string with a real, located entity that
carries its own provenance. TravelTime stores routed distances so the optimizer
no longer estimates delivery time from a straight line.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DemandZone(Base):
    """A customer demand area with a real location.

    Geometry provenance and population provenance are tracked SEPARATELY: a zone
    can have a real OSM centroid while its population is an estimate derived
    from a larger administrative unit.
    """

    __tablename__ = "demand_zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Stable key from the source, e.g. "osm:node/123456".
    external_id: Mapped[str | None] = mapped_column(
        String(80), unique=True, nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(160), index=True)
    zone_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    commune: Mapped[str | None] = mapped_column(String(120), nullable=True)

    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)

    # --- population -------------------------------------------------------
    # NULL when no source provides it. Never filled with a guess.
    population: Mapped[float | None] = mapped_column(Float, nullable=True)
    households: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- provenance, split by field group --------------------------------
    geometry_source_type: Mapped[str] = mapped_column(String(32), default="real_public")
    geometry_source: Mapped[str | None] = mapped_column(String(160), nullable=True)
    population_source_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    population_source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    population_source_date: Mapped[str | None] = mapped_column(
        String(40), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(default=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    __table_args__ = (
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="ck_zone_lat"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="ck_zone_lon"),
        CheckConstraint(
            "population IS NULL OR population >= 0", name="ck_zone_pop_nonneg"
        ),
    )


class TravelTime(Base):
    """A routed store→zone leg.

    `source` records HOW it was produced -- "osrm" for a real road route,
    "haversine_fallback" when the router was unreachable. The two must never be
    confused, so the optimizer and the API both surface this field.
    """

    __tablename__ = "travel_times"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), index=True
    )
    zone_id: Mapped[int] = mapped_column(
        ForeignKey("demand_zones.id", ondelete="CASCADE"), index=True
    )

    distance_km: Mapped[float] = mapped_column(Float)
    travel_time_minutes: Mapped[float] = mapped_column(Float)

    # Picking/packing time added on top of the routed driving time.
    handling_minutes: Mapped[float] = mapped_column(Float, default=0.0)

    source: Mapped[str] = mapped_column(String(60), default="osrm")
    source_type: Mapped[str] = mapped_column(String(32), default="real_public")
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint("store_id", "zone_id", name="uq_travel_store_zone"),
        CheckConstraint("distance_km >= 0", name="ck_travel_dist_nonneg"),
        CheckConstraint("travel_time_minutes >= 0", name="ck_travel_time_nonneg"),
    )

    @property
    def total_minutes(self) -> float:
        return self.travel_time_minutes + self.handling_minutes
