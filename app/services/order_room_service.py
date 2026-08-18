from datetime import datetime, timezone
from decimal import Decimal
from statistics import mean

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import decrypt_content
from app.models.models import Dispute, Order, Review, User
from app.repositories.order_repository import OrderRepository
from app.repositories.order_room_repository import OrderRoomRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.review_repository import ReviewRepository
from app.repositories.user_repository import UserRepository


class OrderRoomService:
    def __init__(self, db: Session):
        self.db = db
        self.orders = OrderRepository(db)
        self.room = OrderRoomRepository(db)
        self.products = ProductRepository(db)
        self.users = UserRepository(db)
        self.reviews = ReviewRepository(db)

    def require_access(self, order_id: int, user_id: int, is_admin: bool = False) -> Order:
        order = self.orders.get_by_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        if not is_admin and user_id not in {order.buyer_id, order.seller_id}:
            raise HTTPException(status_code=403, detail="Access denied")
        return order

    @staticmethod
    def _user_card(user: User) -> dict:
        return {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "rating": float(user.rating or 0),
            "total_sales": int(user.total_sales or 0),
            "is_verified": user.is_verified,
            "created_at": user.created_at,
            "last_active": user.last_active,
        }

    def seller_stats(self, seller_id: int) -> dict:
        orders = self.orders.get_by_seller(seller_id)
        meaningful = [o for o in orders if o.paid_at is not None or o.status in {"paid", "delivered", "completed", "disputed"}]
        completed = [o for o in meaningful if o.status == "completed"]
        cancelled = [o for o in meaningful if o.status == "cancelled"]
        disputed_order_ids = {
            row[0]
            for row in self.db.query(Dispute.order_id)
            .filter(Dispute.order_id.in_([o.id for o in meaningful] or [-1]))
            .distinct()
            .all()
        }
        completion_minutes = [
            (o.completed_at - o.paid_at).total_seconds() / 60
            for o in completed
            if o.completed_at and o.paid_at and o.completed_at >= o.paid_at
        ]
        response_minutes = []
        for order in meaningful[:100]:
            if not order.paid_at:
                continue
            first = self.room.first_seller_message_after(order.id, seller_id, order.paid_at)
            if first and first.created_at >= order.paid_at:
                response_minutes.append((first.created_at - order.paid_at).total_seconds() / 60)
        total = len(meaningful)
        return {
            "orders_total": total,
            "completed": len(completed),
            "cancelled": len(cancelled),
            "disputes": len(disputed_order_ids),
            "success_rate": round((len(completed) / total * 100), 1) if total else None,
            "dispute_rate": round((len(disputed_order_ids) / total * 100), 1) if total else None,
            "avg_completion_minutes": round(mean(completion_minutes), 1) if completion_minutes else None,
            "avg_response_minutes": round(mean(response_minutes), 1) if response_minutes else None,
        }

    def get_room(self, order_id: int, user_id: int, is_admin: bool = False) -> dict:
        order = self.require_access(order_id, user_id, is_admin)
        product = self.products.get_by_id(order.product_id)
        buyer = self.users.get_by_id(order.buyer_id)
        seller = self.users.get_by_id(order.seller_id)
        if not buyer or not seller:
            raise HTTPException(status_code=409, detail="Order participants are unavailable")

        open_dispute = (
            self.db.query(Dispute)
            .filter(Dispute.order_id == order.id, Dispute.status == "open")
            .order_by(Dispute.created_at.desc())
            .first()
        )
        my_review = self.reviews.get_by_order_and_reviewer(order.id, user_id)

        delivery_content = None
        if user_id in {order.buyer_id, order.seller_id} or is_admin:
            if order.delivery_secret:
                try:
                    delivery_content = decrypt_content(order.delivery_secret)
                except Exception:
                    delivery_content = None
            elif order.delivery_info and order.status in {"delivered", "completed", "disputed"}:
                delivery_content = order.delivery_info

        messages = self.room.messages(order.id, limit=200)
        events = self.room.events(order.id, limit=250)
        unread = sum(1 for m in messages if m.sender_id != user_id and not m.is_read)
        is_buyer = user_id == order.buyer_id
        is_seller = user_id == order.seller_id
        product_title = order.product_title_snapshot or (product.title if product else f"Товар #{order.product_id}")
        product_category = order.product_category_snapshot or (product.category if product else None)

        return {
            "order": {
                "id": order.id,
                "buyer_id": order.buyer_id,
                "seller_id": order.seller_id,
                "product_id": order.product_id,
                "product_title": product_title,
                "product_category": product_category,
                "quantity": order.quantity,
                "total_price": Decimal(order.total_price),
                "commission": Decimal(order.commission),
                "seller_earnings": Decimal(order.seller_earnings),
                "status": order.status,
                "created_at": order.created_at,
                "paid_at": order.paid_at,
                "delivered_at": order.delivered_at,
                "completed_at": order.completed_at,
                "cancelled_at": order.cancelled_at,
                "auto_complete_at": order.auto_complete_at,
                "last_activity_at": order.last_activity_at,
                "delivery_content": delivery_content,
                "fulfillment_type": product.fulfillment_type if product else None,
            },
            "buyer": self._user_card(buyer),
            "seller": self._user_card(seller),
            "seller_stats": self.seller_stats(order.seller_id),
            "messages": messages,
            "events": events,
            "open_dispute": open_dispute,
            "my_review": my_review,
            "unread_count": unread,
            "role": "buyer" if is_buyer else "seller" if is_seller else "admin",
            "permissions": {
                "can_pay": is_buyer and order.status == "pending",
                "can_cancel": is_buyer and order.status == "pending",
                "can_deliver": is_seller and order.status == "paid" and (not product or product.fulfillment_type == "manual"),
                "can_confirm": is_buyer and order.status == "delivered",
                "can_dispute": user_id in {order.buyer_id, order.seller_id} and order.status in {"paid", "delivered"} and order.settled_at is None,
                "can_review": user_id in {order.buyer_id, order.seller_id} and order.status == "completed" and my_review is None,
                "can_message": user_id in {order.buyer_id, order.seller_id} and order.status not in {"cancelled"},
            },
        }

    def add_message(self, order_id: int, user_id: int, message: str):
        order = self.require_access(order_id, user_id)
        text = message.strip()
        if not text:
            raise HTTPException(status_code=422, detail="Message is empty")
        if len(text) > 4000:
            raise HTTPException(status_code=422, detail="Message is too long")
        row = self.room.add_message(order.id, user_id, message=text)
        self.db.commit()
        self.db.refresh(row)
        return row

    def add_attachment(self, order_id: int, user_id: int, *, url: str, name: str, mime: str, caption: str | None = None):
        order = self.require_access(order_id, user_id)
        row = self.room.add_message(
            order.id,
            user_id,
            message=(caption.strip() if caption and caption.strip() else None),
            attachment_url=url,
            attachment_name=name,
            attachment_mime=mime,
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def mark_read(self, order_id: int, user_id: int) -> list[int]:
        self.require_access(order_id, user_id)
        ids = self.room.mark_read(order_id, user_id)
        self.db.commit()
        return ids
