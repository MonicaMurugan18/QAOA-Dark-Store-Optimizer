"""Demand endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Demand, Product
from app.schemas import (
    DemandBulkCreate,
    DemandBulkResult,
    DemandCreate,
    DemandRead,
    DemandUpdate,
)

router = APIRouter(prefix="/api/demand", tags=["demand"])


def _require_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"product_id {product_id} does not exist; create the product first",
        )
    return product


def _get_or_404(db: Session, demand_id: int) -> Demand:
    row = db.get(Demand, demand_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"demand id {demand_id} does not exist",
        )
    return row


@router.get("", response_model=list[DemandRead], summary="List demand rows")
def list_demand(
    db: Session = Depends(get_db),
    area: str | None = Query(default=None),
    product_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
) -> list[Demand]:
    stmt = select(Demand).order_by(Demand.area, Demand.product_id)
    if area:
        stmt = stmt.where(Demand.area == area)
    if product_id:
        stmt = stmt.where(Demand.product_id == product_id)
    return list(db.execute(stmt.offset(offset).limit(limit)).scalars())


@router.post(
    "",
    response_model=DemandRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create or replace one demand row",
)
def create_demand(payload: DemandCreate, db: Session = Depends(get_db)) -> Demand:
    _require_product(db, payload.product_id)

    # (area, product_id) is unique. Treat a repeat as an update so the endpoint
    # is idempotent instead of failing on a constraint violation.
    existing = db.execute(
        select(Demand).where(
            Demand.area == payload.area, Demand.product_id == payload.product_id
        )
    ).scalar_one_or_none()

    if existing is not None:
        for key, value in payload.model_dump().items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing

    row = Demand(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post(
    "/bulk",
    response_model=DemandBulkResult,
    summary="Insert or update many demand rows",
)
def bulk_demand(
    payload: DemandBulkCreate, db: Session = Depends(get_db)
) -> DemandBulkResult:
    # Validate every product id BEFORE writing anything, so a bad row cannot
    # leave the table half-updated.
    ids = sorted({item.product_id for item in payload.items})
    found = {
        p.id for p in db.execute(select(Product).where(Product.id.in_(ids))).scalars()
    }
    missing = [i for i in ids if i not in found]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"unknown product_id values, nothing was written: {missing}",
        )

    created = updated = 0
    detail: list[str] = []
    seen: set[tuple[str, int]] = set()

    for item in payload.items:
        key = (item.area, item.product_id)
        if key in seen:
            detail.append(
                f"duplicate (area={item.area!r}, product_id={item.product_id}) "
                f"within the request; the last value wins"
            )
        seen.add(key)

        existing = db.execute(
            select(Demand).where(
                Demand.area == item.area, Demand.product_id == item.product_id
            )
        ).scalar_one_or_none()
        if existing is not None:
            for k, v in item.model_dump().items():
                setattr(existing, k, v)
            updated += 1
        else:
            db.add(Demand(**item.model_dump()))
            created += 1

    db.commit()
    return DemandBulkResult(created=created, updated=updated, skipped=0, detail=detail)


@router.get("/{demand_id}", response_model=DemandRead, summary="Get one demand row")
def get_demand(demand_id: int, db: Session = Depends(get_db)) -> Demand:
    return _get_or_404(db, demand_id)


@router.put("/{demand_id}", response_model=DemandRead, summary="Update a demand row")
def update_demand(
    demand_id: int, payload: DemandUpdate, db: Session = Depends(get_db)
) -> Demand:
    row = _get_or_404(db, demand_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no fields supplied to update",
        )
    if "product_id" in changes:
        _require_product(db, changes["product_id"])
    for key, value in changes.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


@router.delete(
    "/{demand_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a demand row",
)
def delete_demand(demand_id: int, db: Session = Depends(get_db)) -> None:
    row = _get_or_404(db, demand_id)
    db.delete(row)
    db.commit()
