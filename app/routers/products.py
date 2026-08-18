from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_seller
from app.schemas import InventoryAdd, ProductCreate, ProductResponse, ProductUpdate
from app.services.product_service import ProductService

router = APIRouter(prefix="/products", tags=["products"])


@router.get("/", response_model=list[ProductResponse])
def list_products(
    category: str | None = None,
    min_price: Decimal | None = Query(default=None, ge=0),
    max_price: Decimal | None = Query(default=None, ge=0),
    search: str | None = Query(default=None, max_length=200),
    sort: str = Query(default="new", pattern="^(new|price_asc|price_desc|popular|favorites)$"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=400, detail="min_price cannot be greater than max_price")
    return ProductService(db).get_all(category, min_price, max_price, search, sort, skip, limit)


@router.get("/seller/{seller_id}", response_model=list[ProductResponse])
def seller_products(seller_id: int, db: Session = Depends(get_db)):
    return ProductService(db).get_by_seller(seller_id)


@router.post("/", response_model=ProductResponse, status_code=201)
def create_product(data: ProductCreate, seller=Depends(get_current_seller), db: Session = Depends(get_db)):
    return ProductService(db).create(seller.id, data)


@router.post("/{product_id}/inventory")
def add_inventory(product_id: int, data: InventoryAdd, seller=Depends(get_current_seller), db: Session = Depends(get_db)):
    return ProductService(db).add_inventory(product_id, seller.id, data)


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = ProductService(db).get_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.put("/{product_id}", response_model=ProductResponse)
def update_product(product_id: int, data: ProductUpdate, seller=Depends(get_current_seller), db: Session = Depends(get_db)):
    return ProductService(db).update(product_id, data, seller.id)


@router.delete("/{product_id}")
def delete_product(product_id: int, seller=Depends(get_current_seller), db: Session = Depends(get_db)):
    return ProductService(db).delete(product_id, seller.id)
