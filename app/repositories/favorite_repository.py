from sqlalchemy.orm import Session
from app.models.models import Favorite, Product


class FavoriteRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, user_id: int, product_id: int) -> Favorite | None:
        return self.db.query(Favorite).filter(Favorite.user_id == user_id, Favorite.product_id == product_id).first()

    def list_products(self, user_id: int) -> list[Product]:
        return self.db.query(Product).join(Favorite, Favorite.product_id == Product.id).filter(
            Favorite.user_id == user_id,
            Product.status != "deleted",
        ).order_by(Favorite.created_at.desc()).all()
