from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.models import Favorite
from app.repositories.favorite_repository import FavoriteRepository
from app.repositories.product_repository import ProductRepository


class FavoriteService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = FavoriteRepository(db)
        self.products = ProductRepository(db)

    def add(self, user_id: int, product_id: int):
        product = self.products.get_by_id(product_id, for_update=True)
        if not product or product.status == "deleted":
            raise HTTPException(status_code=404, detail="Product not found")
        if self.repo.get(user_id, product_id):
            return {"message": "Already in favorites"}
        self.db.add(Favorite(user_id=user_id, product_id=product_id))
        product.favorites_count = (product.favorites_count or 0) + 1
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            return {"message": "Already in favorites"}
        return {"message": "Added to favorites"}

    def remove(self, user_id: int, product_id: int):
        favorite = self.repo.get(user_id, product_id)
        if not favorite:
            raise HTTPException(status_code=404, detail="Not in favorites")
        product = self.products.get_by_id(product_id, for_update=True)
        self.db.delete(favorite)
        if product:
            product.favorites_count = max(0, (product.favorites_count or 0) - 1)
        self.db.commit()
        return {"message": "Removed from favorites"}

    def get_all(self, user_id: int):
        return self.repo.list_products(user_id)
