"""Data provenance: where every value in this database came from.

THE CORE RULE
=============
A dark store's COORDINATES can be real public data while its OPENING COST is a
prototype assumption. Those two facts must never be blurred together, so
provenance is recorded per FIELD GROUP, not per row.

SourceType is the vocabulary:

    REAL_PUBLIC    observed, publicly available, verifiable (e.g. OpenStreetMap)
    OFFICIAL       published by a government body (e.g. Census of India)
    REAL_BUSINESS  operator's own data, obtained with authorisation
    PROXY          a real measured quantity standing in for the one we want
                   (e.g. population used in place of customer orders)
    ESTIMATED      derived from real inputs by a documented formula
    SYNTHETIC      invented for the prototype; carries no real-world claim

Nothing in this codebase may present SYNTHETIC or PROXY data as REAL.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database import Base


class SourceType(str, enum.Enum):
    REAL_PUBLIC = "real_public"
    OFFICIAL = "official"
    REAL_BUSINESS = "real_business"
    PROXY = "proxy"
    ESTIMATED = "estimated"
    SYNTHETIC = "synthetic"

    @property
    def is_real(self) -> bool:
        return self in (
            SourceType.REAL_PUBLIC,
            SourceType.OFFICIAL,
            SourceType.REAL_BUSINESS,
        )


#: Human-readable explanation shown in the API and the dashboard.
SOURCE_TYPE_DESCRIPTION = {
    SourceType.REAL_PUBLIC.value:
        "Observed public data from a verifiable source.",
    SourceType.OFFICIAL.value:
        "Published by a government body.",
    SourceType.REAL_BUSINESS.value:
        "Operator's own records, obtained with authorisation.",
    SourceType.PROXY.value:
        "A real measured quantity standing in for the one actually wanted.",
    SourceType.ESTIMATED.value:
        "Derived from real inputs by a documented, configurable formula.",
    SourceType.SYNTHETIC.value:
        "Invented for the prototype. Carries no real-world claim.",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DataSource(Base):
    """One registered dataset and everything needed to judge its credibility."""

    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Stable machine key, e.g. "osm_stores", "census_population".
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)

    dataset: Mapped[str] = mapped_column(String(160))
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    source_name: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # The date the UNDERLYING DATA refers to -- not the date we downloaded it.
    # Census 2011 stays 2011 no matter when it is ingested.
    source_date: Mapped[str | None] = mapped_column(String(40), nullable=True)

    licence: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ingested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    record_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(40), default="not_loaded")

    # Why this dataset is trustworthy, or exactly what its limits are.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # What it feeds: "stores", "demand_zones", "products", "travel_times", ...
    feeds: Mapped[str | None] = mapped_column(String(200), nullable=True)

    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "dataset": self.dataset,
            "source_type": self.source_type,
            "source_type_description": SOURCE_TYPE_DESCRIPTION.get(
                self.source_type, ""
            ),
            "is_real": self.source_type
            in {
                SourceType.REAL_PUBLIC.value,
                SourceType.OFFICIAL.value,
                SourceType.REAL_BUSINESS.value,
            },
            "source_name": self.source_name,
            "source_url": self.source_url,
            "source_date": self.source_date,
            "licence": self.licence,
            "ingested_at": self.ingested_at.isoformat() if self.ingested_at else None,
            "record_count": self.record_count,
            "status": self.status,
            "feeds": self.feeds,
            "notes": self.notes,
            "extra": self.extra,
        }


class DataIngestionRun(Base):
    """An execution of the ingestion pipeline, with per-dataset counts.

    Rejected records are COUNTED AND LOGGED here, never silently dropped.
    """

    __tablename__ = "data_ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="running")

    # Which ingesters were asked to run.
    requested: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # {dataset: {fetched, inserted, updated, rejected, rejections: [...]}}
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "status": self.status,
            "requested": self.requested,
            "report": self.report,
            "error_message": self.error_message,
        }
