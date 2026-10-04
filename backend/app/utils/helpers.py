"""Geometry, travel-time and small shared utilities."""

from __future__ import annotations

import math

# Straight-line distance underestimates road distance. 1.30 is a typical
# circuity factor for a small, fairly gridded Indian town.
CIRCUITY_FACTOR = 1.30

# Scooter speed in dense urban traffic, and the fixed picking/packing time that
# every order costs before a rider leaves the store.
AVG_SPEED_KMPH = 20.0
HANDLING_MIN = 3.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def road_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return haversine_km(lat1, lon1, lat2, lon2) * CIRCUITY_FACTOR


def delivery_time_min(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    speed_kmph: float = AVG_SPEED_KMPH,
    handling_min: float = HANDLING_MIN,
) -> float:
    """Door-to-door minutes: picking time plus travel.

    Handling time is included on purpose. Without it a store sitting on top of
    an area would show a 0-minute delivery, which is not physically possible and
    would make that pair win every assignment for free.
    """
    km = road_distance_km(lat1, lon1, lat2, lon2)
    return handling_min + (km / speed_kmph) * 60.0


def area_centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Mean latitude/longitude of a set of points.

    Adequate for a town-sized bounding box; not a projected centroid.
    """
    if not points:
        raise ValueError("area_centroid requires at least one point")
    return (
        sum(p[0] for p in points) / len(points),
        sum(p[1] for p in points) / len(points),
    )


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Division that returns `default` instead of raising on a zero divisor."""
    if denominator in (0, 0.0):
        return default
    return numerator / denominator


def percent_gap(value: float, reference: float) -> float | None:
    """Signed percentage gap of `value` against `reference`.

    Returns None when the reference is zero, because a percentage gap from zero
    is undefined rather than infinite.
    """
    if reference == 0:
        return None
    return 100.0 * (value - reference) / abs(reference)
