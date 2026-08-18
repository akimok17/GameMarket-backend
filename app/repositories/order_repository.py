from datetime import datetime
from sqlalchemy.orm import Session

from app.models.models import Order


class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, order_id: int, *, for_update: bool = False) -> Order | None:
        query = self.db.query(Order).filter(Order.id == order_id)
        if for_update:
            query = query.with_for_update()
        return query.first()

    def create(self, **data) -> Order:
        order = Order(**data)
        self.db.add(order)
        self.db.flush()
        return order

    def get_by_buyer(self, buyer_id: int) -> list[Order]:
        return self.db.query(Order).filter(Order.buyer_id == buyer_id).order_by(Order.created_at.desc()).all()

    def get_by_seller(self, seller_id: int) -> list[Order]:
        return self.db.query(Order).filter(Order.seller_id == seller_id).order_by(Order.created_at.desc()).all()

    def get_overdue(self, now: datetime) -> list[Order]:
        return self.db.query(Order).filter(
            Order.status == "delivered",
            Order.auto_complete_at.is_not(None),
            Order.auto_complete_at <= now,
            Order.settled_at.is_(None),
        ).with_for_update(skip_locked=True).all()
