"""Store endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Store
from app.schemas import StoreCreate, StoreRead, StoreUpdate

router = APIRouter(prefix="/api/stores", tags=["stores"])


def _get_or_404(db: Session, store_id: int) -> Store:
    store = db.get(Store, store_id)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"store id {store_id} does not exist",
        )
    return store


@router.get("", response_model=list[StoreRead], summary="List stores")
def list_stores(
    db: Session = Depends(get_db),
    area: str | None = Query(default=None, description="Filter by area name"),
    candidates_only: bool = Query(
        default=False, description="Only stores eligible for optimization"
    ),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[Store]:
    stmt = select(Store).order_by(Store.id)
    if area:
        stmt = stmt.where(Store.area == area)
    if candidates_only:
        stmt = stmt.where(Store.is_candidate.is_(True))
    return list(db.execute(stmt.offset(offset).limit(limit)).scalars())


@router.get("/{store_id}", response_model=StoreRead, summary="Get one store")
def get_store(store_id: int, db: Session = Depends(get_db)) -> Store:
    return _get_or_404(db, store_id)


@router.post(
    "",
    response_model=StoreRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a store",
)
def create_store(payload: StoreCreate, db: Session = Depends(get_db)) -> Store:
    store = Store(**payload.model_dump())
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


@router.put("/{store_id}", response_model=StoreRead, summary="Update a store")
def update_store(
    store_id: int, payload: StoreUpdate, db: Session = Depends(get_db)
) -> Store:
    store = _get_or_404(db, store_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no fields supplied to update",
        )
    for key, value in changes.items():
        setattr(store, key, value)
    db.commit()
    db.refresh(store)
    return store


@router.delete(
    "/{store_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a store"
)
def delete_store(store_id: int, db: Session = Depends(get_db)) -> None:
    store = _get_or_404(db, store_id)
    db.delete(store)
    db.commit()
