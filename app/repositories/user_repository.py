from decimal import Decimal
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: int, *, for_update: bool = False) -> User | None:
        query = self.db.query(User).filter(User.id == user_id)
        if for_update:
            query = query.with_for_update()
        return query.first()

    def get_by_username(self, username: str) -> User | None:
        return self.db.query(User).filter(func.lower(User.username) == username.lower()).first()

    def get_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(func.lower(User.email) == email.lower()).first()

    def get_by_phone(self, phone: str) -> User | None:
        return self.db.query(User).filter(User.phone == phone).first()

    def create(self, **data) -> User:
        user = User(**data)
        self.db.add(user)
        self.db.flush()
        return user

    def adjust_balance(self, user_id: int, amount: Decimal) -> User:
        user = self.get_by_id(user_id, for_update=True)
        if not user:
            raise LookupError("User not found")
        user.balance = Decimal(user.balance or 0) + amount
        self.db.flush()
        return user
