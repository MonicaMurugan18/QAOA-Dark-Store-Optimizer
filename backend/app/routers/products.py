"""Product endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Demand, Product
from app.schemas import ProductCreate, ProductRead, ProductUpdate

router = APIRouter(prefix="/api/products", tags=["products"])


def _get_or_404(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"product id {product_id} does not exist",
        )
    return product


@router.get("", response_model=list[ProductRead], summary="List products")
def list_products(
    db: Session = Depends(get_db),
    category: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[Product]:
    stmt = select(Product).order_by(Product.id)
    if category:
        stmt = stmt.where(Product.category == category)
    return list(db.execute(stmt.offset(offset).limit(limit)).scalars())


@router.get("/{product_id}", response_model=ProductRead, summary="Get one product")
def get_product(product_id: int, db: Session = Depends(get_db)) -> Product:
    return _get_or_404(db, product_id)


@router.post(
    "",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a product",
)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)) -> Product:
    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.put("/{product_id}", response_model=ProductRead, summary="Update a product")
def update_product(
    product_id: int, payload: ProductUpdate, db: Session = Depends(get_db)
) -> Product:
    product = _get_or_404(db, product_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no fields supplied to update",
        )
    for key, value in changes.items():
        setattr(product, key, value)
    db.commit()
    db.refresh(product)
    return product


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a product",
)
def delete_product(product_id: int, db: Session = Depends(get_db)) -> None:
    product = _get_or_404(db, product_id)

    # Demand rows cascade with the product. Say so plainly rather than letting
    # the caller discover that demand silently disappeared.
    linked = db.execute(
        select(Demand).where(Demand.product_id == product_id).limit(1)
    ).scalar_one_or_none()
    if linked is not None:
        db.query(Demand).filter(Demand.product_id == product_id).delete()

    db.delete(product)
    db.commit()
