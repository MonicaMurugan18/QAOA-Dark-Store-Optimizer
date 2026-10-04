"""ORM models. Importing this package registers every mapper."""

from app.models.demand import Demand
from app.models.geo import DemandZone, TravelTime
from app.models.optimization import (
    Method,
    OptimizationResult,
    OptimizationRun,
    RunStatus,
)
from app.models.product import Product
from app.models.provenance import (
    SOURCE_TYPE_DESCRIPTION,
    DataIngestionRun,
    DataSource,
    SourceType,
)
from app.models.store import Store

__all__ = [
    "SOURCE_TYPE_DESCRIPTION",
    "DataIngestionRun",
    "DataSource",
    "Demand",
    "DemandZone",
    "Method",
    "OptimizationResult",
    "OptimizationRun",
    "Product",
    "RunStatus",
    "SourceType",
    "Store",
    "TravelTime",
]
