"""Shared ingestion machinery: reporting, validation, HTTP.

REJECTED RECORDS ARE NEVER SILENTLY DROPPED. Every rejection is counted and
logged with the reason and the offending payload, and the whole list is stored
on the DataIngestionRun row so it can be inspected after the fact.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("darkstore.ingestion")

#: Puducherry mainland bounding box (south, west, north, east).
#: Deliberately EXCLUDES the Mahé (Kerala) and Yanam (Andhra Pradesh) exclaves,
#: which belong to the same union territory but are hundreds of km away. An
#: Overpass area query on "Puducherry" returns them and they would corrupt every
#: distance calculation, so they are filtered out here and the rejection logged.
PUDUCHERRY_BBOX = (11.87, 79.74, 12.06, 79.88)

RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parents[3] / "data" / "processed"
RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = "qaoa-darkstore-research/0.1 (academic project; contact via repo)"


# ===========================================================================
# Reporting
# ===========================================================================
@dataclass
class IngestionReport:
    dataset: str
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    rejected: int = 0
    rejections: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_key: str | None = None
    skipped_reason: str | None = None

    def reject(self, reason: str, payload: dict | str) -> None:
        """Record a rejected record. Always logged, never discarded quietly."""
        self.rejected += 1
        entry = {"reason": reason, "record": payload}
        # Cap what is persisted so a bad feed cannot bloat the run row, but keep
        # the full COUNT accurate.
        if len(self.rejections) < 200:
            self.rejections.append(entry)
        logger.warning("[%s] rejected: %s | %s", self.dataset, reason, payload)

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        logger.warning("[%s] %s", self.dataset, message)

    def to_dict(self) -> dict:
        return {
            "dataset": self.dataset,
            "fetched": self.fetched,
            "inserted": self.inserted,
            "updated": self.updated,
            "rejected": self.rejected,
            "rejection_sample": self.rejections[:25],
            "rejections_recorded": len(self.rejections),
            "warnings": self.warnings,
            "source_key": self.source_key,
            "skipped_reason": self.skipped_reason,
        }


class IngestionError(RuntimeError):
    """A source could not be reached or parsed. Surfaced, never swallowed."""


# ===========================================================================
# Validation helpers
# ===========================================================================
def valid_coordinate(lat, lon) -> tuple[bool, str]:
    """Structural validity, independent of any bounding box."""
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return False, "latitude/longitude missing or not numeric"
    if not (-90 <= lat <= 90):
        return False, f"latitude {lat} out of range"
    if not (-180 <= lon <= 180):
        return False, f"longitude {lon} out of range"
    if lat == 0 and lon == 0:
        return False, "null island (0,0) coordinate"
    return True, ""


def inside_bbox(lat: float, lon: float, bbox=PUDUCHERRY_BBOX) -> bool:
    s, w, n, e = bbox
    return s <= lat <= n and w <= lon <= e


def non_negative(value, label: str) -> tuple[bool, str]:
    if value is None:
        return False, f"{label} is missing"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False, f"{label} is not numeric: {value!r}"
    if v < 0:
        return False, f"{label} is negative: {v}"
    return True, ""


def require(value, label: str) -> tuple[bool, str]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return False, f"{label} is missing"
    return True, ""


# ===========================================================================
# HTTP
# ===========================================================================
def http_get(url: str, *, timeout: int = 90, accept: str | None = None) -> bytes:
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise IngestionError(f"HTTP {exc.code} from {url}: {exc.reason}") from exc
    except Exception as exc:
        raise IngestionError(f"{type(exc).__name__} fetching {url}: {exc}") from exc


def http_post_form(url: str, data: dict, *, timeout: int = 180) -> bytes:
    req = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(data).encode(),
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise IngestionError(f"HTTP {exc.code} from {url}: {exc.reason}") from exc
    except Exception as exc:
        raise IngestionError(f"{type(exc).__name__} posting to {url}: {exc}") from exc


def overpass(query: str, *, cache_name: str, use_cache: bool = True) -> dict:
    """Run an Overpass query, caching the raw response to data/raw/.

    The cache keeps re-runs cheap and means the pipeline is reproducible without
    hammering a free community endpoint.
    """
    cache = RAW_DIR / f"{cache_name}.json"
    if use_cache and cache.exists():
        logger.info("overpass: using cached %s", cache.name)
        return json.loads(cache.read_text(encoding="utf-8"))

    logger.info("overpass: querying live (%s)", cache_name)
    raw = http_post_form(
        "https://overpass-api.de/api/interpreter", {"data": query}, timeout=240
    )
    payload = json.loads(raw)
    cache.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return payload


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def polite_sleep(seconds: float) -> None:
    """Rate-limit courtesy for free public endpoints."""
    time.sleep(seconds)
