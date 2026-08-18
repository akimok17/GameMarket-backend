from sqlalchemy.orm import Session

from app.models.models import PaymentDeposit


class PaymentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_deposit(self, **data) -> PaymentDeposit:
        item = PaymentDeposit(**data)
        self.db.add(item)
        self.db.flush()
        return item

    def get_deposit(self, deposit_id: int, *, for_update: bool = False) -> PaymentDeposit | None:
        query = self.db.query(PaymentDeposit).filter(PaymentDeposit.id == deposit_id)
        if for_update:
            query = query.with_for_update()
        return query.first()

    def get_by_idempotency_key(self, key: str) -> PaymentDeposit | None:
        return self.db.query(PaymentDeposit).filter(PaymentDeposit.idempotency_key == key).first()

    def get_by_provider_payment_id(self, provider_payment_id: str, *, for_update: bool = False) -> PaymentDeposit | None:
        query = self.db.query(PaymentDeposit).filter(PaymentDeposit.provider_payment_id == provider_payment_id)
        if for_update:
            query = query.with_for_update()
        return query.first()

    def list_user_deposits(self, user_id: int, limit: int = 50) -> list[PaymentDeposit]:
        return (
            self.db.query(PaymentDeposit)
            .filter(PaymentDeposit.user_id == user_id)
            .order_by(PaymentDeposit.created_at.desc(), PaymentDeposit.id.desc())
            .limit(limit)
            .all()
        )
