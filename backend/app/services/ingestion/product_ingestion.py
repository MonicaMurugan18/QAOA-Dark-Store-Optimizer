"""Product catalogue from a real quick-commerce platform export.

SOURCE
======
`quickcommerce-sample-blinkit-products-<date>.xlsx` -- a public sample export of
a Blinkit product catalogue supplied with this project. Columns observed:

    Product ID, Platform, Name, Brand, MRP, Category, Subcategory,
    Quantity, Updated at, Image URL, Deeplink

WHAT IS REAL, AND WHAT IS DERIVED
=================================
REAL (from the catalogue):
    product id, platform, name, brand, category, subcategory, pack quantity,
    MRP, catalogue timestamp

DERIVED, and labelled `estimated`:
    unit_volume -- the optimizer needs shelf space per unit. The catalogue gives
        a pack size string ("500 g", "750 ml", "1 pc"). We parse it and convert
        to litres-equivalent by a documented rule (see `parse_pack_volume`).
        Solids are converted at 1 g -> 1 ml, which is a stated approximation.

    unit_cost -- the optimizer needs SUPPLIER cost; the catalogue gives MRP,
        which is RETAIL price. We derive cost = MRP * (1 - assumed margin).
        The margin is configurable and the field is labelled `estimated`.
        It is NOT an observed wholesale price.
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product, SourceType
from app.services.ingestion.base import IngestionReport, non_negative, require

SOURCE_KEY = "blinkit_catalogue"
SOURCE_NAME = "Blinkit product catalogue sample (public export)"

#: Retail margin assumed when converting MRP to a supplier cost.
#: Documented and configurable; the result is labelled `estimated`.
ASSUMED_RETAIL_MARGIN = 0.22

#: Litres-equivalent per unit for pack sizes we cannot parse.
#: Used only when the pack string is unreadable, and the row is flagged.
FALLBACK_UNIT_VOLUME = 0.5

_UNIT_TO_LITRES = {
    "l": 1.0,
    "ltr": 1.0,
    "litre": 1.0,
    "liter": 1.0,
    "ml": 0.001,
    # Mass -> volume at the density of water. An explicit approximation: it is
    # right for liquids and close enough for most packaged groceries.
    "kg": 1.0,
    "g": 0.001,
    "gm": 0.001,
    "gms": 0.001,
}


def parse_pack_volume(quantity: str) -> tuple[float | None, str]:
    """Convert a pack-size string to litres-equivalent.

    Returns (volume, rule_applied). Volume is None when the string cannot be
    parsed -- the caller then rejects or flags the row rather than guessing.
    """
    if not quantity:
        return None, "empty pack size"
    q = str(quantity).strip().lower().replace(",", "")

    # "2 x 500 ml" style multipacks
    multi = re.match(r"^\s*(\d+(?:\.\d+)?)\s*[x*]\s*(\d+(?:\.\d+)?)\s*([a-z]+)", q)
    if multi:
        count, size, unit = float(multi[1]), float(multi[2]), multi[3]
        if unit in _UNIT_TO_LITRES:
            return count * size * _UNIT_TO_LITRES[unit], f"{count}x{size}{unit}"

    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*([a-z]+)", q)
    if m:
        value, unit = float(m[1]), m[2]
        if unit in _UNIT_TO_LITRES:
            return value * _UNIT_TO_LITRES[unit], f"{value}{unit}"
        # Countable units: "1 pc", "12 pieces", "1 pack"
        if unit in {"pc", "pcs", "piece", "pieces", "pack", "unit", "units", "n"}:
            # One countable item is assumed to occupy 0.4 L of shelf space.
            return value * 0.4, f"{value} countable @0.4L"
    return None, f"unparseable pack size {quantity!r}"


def find_catalogue_file(explicit: str | None = None) -> Path | None:
    """Locate the catalogue export. Never invents a file."""
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None
    candidates = [
        Path.home() / "Downloads",
        Path(__file__).resolve().parents[3] / "data" / "raw",
    ]
    for folder in candidates:
        if not folder.exists():
            continue
        hits = sorted(folder.glob("quickcommerce-sample-*products*.xlsx"))
        if hits:
            return hits[-1]
    return None


def ingest_products(
    db: Session, *, file_path: str | None = None, limit: int | None = None
) -> IngestionReport:
    report = IngestionReport(dataset="products", source_key=SOURCE_KEY)

    path = find_catalogue_file(file_path)
    if path is None:
        report.skipped_reason = (
            "no quickcommerce catalogue export found. Place a "
            "'quickcommerce-sample-*products*.xlsx' file in backend/data/raw/ "
            "or ~/Downloads and re-run. Existing products are left untouched."
        )
        report.warn(report.skipped_reason)
        return report

    import pandas as pd

    df = pd.read_excel(path)
    report.fetched = len(df)
    report.warn(f"catalogue file: {path.name}")

    # The export's own timestamp is the catalogue date, not today.
    cat_date = None
    if "Updated at" in df.columns and len(df):
        try:
            cat_date = str(pd.to_datetime(df["Updated at"]).max().date())
        except Exception:
            cat_date = None
    if cat_date is None:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
        cat_date = m[1] if m else None

    seen: set[str] = set()
    rows = df.head(limit) if limit else df

    for _, row in rows.iterrows():
        pid = row.get("Product ID")
        name = str(row.get("Name") or "").strip()
        ext = f"blinkit:{pid}"

        ok, why = require(name, "product name")
        if not ok:
            report.reject(why, {"product_id": str(pid)})
            continue
        if ext in seen:
            report.reject("duplicate product id in this feed", {"product_id": str(pid)})
            continue
        seen.add(ext)

        mrp = row.get("MRP")
        ok, why = non_negative(mrp, "MRP")
        if not ok:
            report.reject(why, {"product_id": str(pid), "name": name})
            continue
        mrp = float(mrp)

        volume, rule = parse_pack_volume(row.get("Quantity"))
        volume_flagged = False
        if volume is None or volume <= 0:
            volume = FALLBACK_UNIT_VOLUME
            volume_flagged = True
            report.warn(
                f"{name[:40]!r}: {rule}; fell back to {FALLBACK_UNIT_VOLUME} L "
                f"and flagged the row"
            )

        # MRP is RETAIL. Supplier cost is derived, and labelled as such.
        unit_cost = round(mrp * (1.0 - ASSUMED_RETAIL_MARGIN), 2)

        values = dict(
            name=name[:120],
            category=str(row.get("Category") or "Uncategorised")[:80],
            subcategory=str(row.get("Subcategory") or "")[:120] or None,
            brand=str(row.get("Brand") or "")[:120] or None,
            platform=str(row.get("Platform") or "")[:60] or None,
            pack_quantity=str(row.get("Quantity") or "")[:60] or None,
            mrp_inr=mrp,
            unit_volume=round(volume, 4),
            unit_cost=unit_cost,
            data_source="BLINKIT_CATALOGUE_REAL+DERIVED_VOLUME_COST",
            catalogue_source_type=SourceType.REAL_PUBLIC.value,
            source_name=SOURCE_NAME,
            source_date=cat_date,
            volume_source_type=(
                SourceType.SYNTHETIC.value
                if volume_flagged
                else SourceType.ESTIMATED.value
            ),
            cost_source_type=SourceType.ESTIMATED.value,
        )

        existing = db.execute(
            select(Product).where(Product.external_id == ext)
        ).scalar_one_or_none()
        if existing:
            for k, v in values.items():
                setattr(existing, k, v)
            report.updated += 1
        else:
            db.add(Product(external_id=ext, **values))
            report.inserted += 1

    db.commit()
    report.warn(
        f"unit_cost derived from MRP assuming a {ASSUMED_RETAIL_MARGIN:.0%} "
        f"retail margin -- this is an ESTIMATE, not an observed wholesale price"
    )
    report.warn(
        "unit_volume derived from the pack-size string; solids converted at "
        "1 g -> 1 ml, a stated approximation"
    )
    return report


SOURCE_META = {
    "key": SOURCE_KEY,
    "dataset": "Product catalogue",
    "source_type": SourceType.REAL_PUBLIC.value,
    "source_name": SOURCE_NAME,
    "source_url": "https://blinkit.com/ (catalogue sample export)",
    "licence": "sample export supplied with the project; platform catalogue data",
    "feeds": "products (name, brand, category, pack size, MRP)",
    "notes": (
        "Real platform catalogue sample. Names, brands, categories, pack sizes "
        "and MRP are observed. unit_volume and unit_cost are DERIVED by "
        "documented rules and labelled estimated -- the catalogue publishes "
        "retail MRP, not supplier cost or shelf volume."
    ),
}
