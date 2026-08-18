from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.security import encrypt_content
from app.models.models import Product
from app.repositories.product_repository import ProductRepository
from app.repositories.user_repository import UserRepository
from app.schemas import InventoryAdd, ProductCreate, ProductUpdate


class ProductService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ProductRepository(db)
        self.user_repo = UserRepository(db)

    def create(self, seller_id: int, data: ProductCreate):
        seller = self.user_repo.get_by_id(seller_id)
        if not seller or not seller.is_seller:
            raise HTTPException(status_code=403, detail="Seller access required")
        if data.fulfillment_type == "manual" and data.digital_items:
            raise HTTPException(status_code=400, detail="Manual products cannot contain automatic inventory")
        if data.fulfillment_type == "automatic":
            stock_quantity = len(data.digital_items)
        else:
            stock_quantity = data.stock_quantity
        product = self.repo.create(
            seller_id=seller_id,
            title=data.title.strip(),
            description=data.description.strip() if data.description else None,
            category=data.category.strip() if data.category else None,
            price=data.price,
            old_price=data.old_price,
            fulfillment_type=data.fulfillment_type,
            delivery_time=data.delivery_time.strip() if data.delivery_time else None,
            stock_quantity=stock_quantity,
            tags=[x.strip()[:50] for x in data.tags if x.strip()],
            status="active",
        )
        if data.digital_items:
            self.repo.add_inventory(product.id, [encrypt_content(x) for x in data.digital_items])
        self.db.commit()
        self.db.refresh(product)
        return product

    def update(self, product_id: int, data: ProductUpdate, seller_id: int):
        product = self.repo.get_by_id(product_id, for_update=True)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        if product.seller_id != seller_id:
            raise HTTPException(status_code=403, detail="Access denied")
        payload = data.model_dump(exclude_unset=True)
        if product.fulfillment_type == "automatic":
            payload.pop("stock_quantity", None)
        for key, value in payload.items():
            if isinstance(value, str):
                value = value.strip()
            setattr(product, key, value)
        self.db.commit()
        self.db.refresh(product)
        return product

    def delete(self, product_id: int, seller_id: int):
        product = self.repo.get_by_id(product_id, for_update=True)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        if product.seller_id != seller_id:
            raise HTTPException(status_code=403, detail="Access denied")
        product.status = "deleted"
        self.db.commit()
        return {"message": "Product deleted"}

    def add_inventory(self, product_id: int, seller_id: int, data: InventoryAdd):
        product = self.repo.get_by_id(product_id, for_update=True)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        if product.seller_id != seller_id:
            raise HTTPException(status_code=403, detail="Access denied")
        if product.fulfillment_type != "automatic":
            raise HTTPException(status_code=400, detail="Inventory is only available for automatic products")
        added = self.repo.add_inventory(product.id, [encrypt_content(x) for x in data.items])
        product.stock_quantity = self.repo.count_available_inventory(product.id)
        self.db.commit()
        return {"message": "Inventory added", "added": added, "stock_quantity": product.stock_quantity}

    def get_all(self, category=None, min_price: Decimal | None = None, max_price: Decimal | None = None,
                search=None, sort="new", skip=0, limit=20):
        return self.repo.list_active(
            category=category, min_price=min_price, max_price=max_price,
            search=search, sort=sort, skip=skip, limit=limit,
        )

    def get_by_id(self, product_id: int, *, count_view: bool = True):
        product = self.repo.get_by_id(product_id)
        if not product or product.status == "deleted":
            return None
        if count_view:
            self.db.execute(update(Product).where(Product.id == product_id).values(views_count=Product.views_count + 1))
            self.db.commit()
            self.db.refresh(product)
        return product

    def get_by_seller(self, seller_id: int, requester_id: int | None = None):
        return self.repo.get_by_seller(seller_id, include_deleted=False)
