import re
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories.order_repository import OrderRepository
from app.repositories.order_room_repository import OrderRoomRepository
from app.repositories.review_repository import ReviewRepository
from app.repositories.user_repository import UserRepository
from app.schemas import ProfileUpdate, ReviewCreate


def normalize_phone(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if value.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if len(digits) < 8 or len(digits) > 15:
        raise HTTPException(status_code=422, detail="Invalid phone number")
    return "+" + digits



class ProfileService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)
        self.orders = OrderRepository(db)
        self.reviews = ReviewRepository(db)
        self.room = OrderRoomRepository(db)

    def public_profile(self, user_id: int):
        user = self.users.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        received = self.reviews.get_by_target_user(user_id)
        avg = sum(x.rating for x in received) / len(received) if received else 0
        return {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "is_seller": user.is_seller,
            "is_verified": user.is_verified,
            "rating": float(avg),
            "total_sales": user.total_sales,
            "reviews_count": len(received),
            "created_at": user.created_at,
        }

    def my_profile(self, user_id: int):
        user = self.users.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        data = self.public_profile(user_id)
        buyer_orders = self.orders.get_by_buyer(user_id)
        seller_orders = self.orders.get_by_seller(user_id)
        data.update({
            "email": user.email,
            "phone": user.phone,
            "email_verified": bool(user.email_verified_at),
            "phone_verified": bool(user.phone_verified_at),
            "email_verified_at": user.email_verified_at,
            "phone_verified_at": user.phone_verified_at,
            "balance": Decimal(user.balance or 0),
            "balance_frozen": Decimal(user.balance_frozen or 0),
            "withdrawable_balance": Decimal(getattr(user, "withdrawable_balance", 0) or 0),
            "total_orders": len({o.id for o in buyer_orders + seller_orders}),
        })
        return data

    def update(self, user_id: int, data: ProfileUpdate):
        user = self.users.get_by_id(user_id, for_update=True)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if data.email is not None:
            email = str(data.email).strip().lower()
            existing = self.users.get_by_email(email)
            if existing and existing.id != user_id:
                raise HTTPException(status_code=409, detail="Email already taken")
            if email != user.email:
                user.email = email
                user.email_verified_at = None
        if data.full_name is not None:
            user.full_name = data.full_name.strip() or None
        if data.phone is not None:
            phone = normalize_phone(data.phone)
            if phone:
                existing_phone = self.users.get_by_phone(phone)
                if existing_phone and existing_phone.id != user_id:
                    raise HTTPException(status_code=409, detail="Phone already taken")
            if phone != user.phone:
                user.phone = phone
                user.phone_verified_at = None
        self.db.commit()
        self.db.refresh(user)
        return self.my_profile(user_id)

    def get_reviews(self, user_id: int):
        if not self.users.get_by_id(user_id):
            raise HTTPException(status_code=404, detail="User not found")
        return self.reviews.get_by_target_user(user_id)

    def create_review(self, reviewer_id: int, data: ReviewCreate):
        order = self.orders.get_by_id(data.order_id)
        if not order or order.status != "completed":
            raise HTTPException(status_code=409, detail="Order must be completed")
        if reviewer_id not in {order.buyer_id, order.seller_id}:
            raise HTTPException(status_code=403, detail="You are not part of this order")
        if self.reviews.get_by_order_and_reviewer(order.id, reviewer_id):
            raise HTTPException(status_code=409, detail="Review already exists")
        target_id = order.seller_id if reviewer_id == order.buyer_id else order.buyer_id
        review = self.reviews.create(
            reviewer_id=reviewer_id,
            target_user_id=target_id,
            order_id=order.id,
            rating=data.rating,
            comment=data.comment.strip() if data.comment else None,
        )
        target = self.users.get_by_id(target_id, for_update=True)
        self.db.flush()
        avg = self.reviews.average_for_user(target_id)
        target.rating = Decimal(str(avg or 0)).quantize(Decimal("0.01"))
        self.room.add_event(order.id, "review", f"Оставлен отзыв: {data.rating}/5", actor_id=reviewer_id, payload={"rating": data.rating})
        self.db.commit()
        self.db.refresh(review)
        return review
