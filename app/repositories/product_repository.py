from decimal import Decimal
from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Session

from app.models.models import DigitalItem, Product


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, product_id: int, *, for_update: bool = False) -> Product | None:
        query = self.db.query(Product).filter(Product.id == product_id)
        if for_update:
            query = query.with_for_update()
        return query.first()

    def list_active(self, *, category: str | None = None, min_price: Decimal | None = None,
                    max_price: Decimal | None = None, search: str | None = None,
                    sort: str = "new", skip: int = 0, limit: int = 20) -> list[Product]:
        query = self.db.query(Product).filter(Product.status == "active")
        if category:
            query = query.filter(Product.category == category)
        if min_price is not None:
            query = query.filter(Product.price >= min_price)
        if max_price is not None:
            query = query.filter(Product.price <= max_price)
        if search:
            pattern = f"%{search.strip()}%"
            query = query.filter((Product.title.ilike(pattern)) | (Product.description.ilike(pattern)))
        ordering = {
            "price_asc": asc(Product.price),
            "price_desc": desc(Product.price),
            "popular": desc(Product.views_count),
            "favorites": desc(Product.favorites_count),
            "new": desc(Product.created_at),
        }.get(sort, desc(Product.created_at))
        return query.order_by(ordering, desc(Product.id)).offset(skip).limit(limit).all()

    def get_by_seller(self, seller_id: int, *, include_deleted: bool = False) -> list[Product]:
        query = self.db.query(Product).filter(Product.seller_id == seller_id)
        if not include_deleted:
            query = query.filter(Product.status != "deleted")
        return query.order_by(Product.created_at.desc()).all()

    def create(self, **data) -> Product:
        product = Product(**data)
        self.db.add(product)
        self.db.flush()
        return product

    def add_inventory(self, product_id: int, encrypted_items: list[str]) -> int:
        self.db.add_all([DigitalItem(product_id=product_id, encrypted_content=item) for item in encrypted_items])
        self.db.flush()
        return len(encrypted_items)

    def available_inventory(self, product_id: int, *, limit: int, for_update: bool = False) -> list[DigitalItem]:
        query = self.db.query(DigitalItem).filter(
            DigitalItem.product_id == product_id,
            DigitalItem.status == "available",
        ).order_by(DigitalItem.id).limit(limit)
        if for_update:
            query = query.with_for_update(skip_locked=True)
        return query.all()

    def count_available_inventory(self, product_id: int) -> int:
        return self.db.query(func.count(DigitalItem.id)).filter(
            DigitalItem.product_id == product_id,
            DigitalItem.status == "available",
        ).scalar() or 0
