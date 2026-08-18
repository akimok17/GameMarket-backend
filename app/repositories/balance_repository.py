from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.models import BalanceHistory, WithdrawalRequest


class BalanceRepository:
    def __init__(self, db: Session):
        self.db = db

    def add_history(self, user_id: int, amount: Decimal, type: str, description: str,
                    reference_type: str | None = None, reference_id: int | None = None) -> BalanceHistory:
        entry = BalanceHistory(
            user_id=user_id, amount=amount, type=type, description=description,
            reference_type=reference_type, reference_id=reference_id,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def get_history(self, user_id: int, limit: int = 100) -> list[BalanceHistory]:
        return self.db.query(BalanceHistory).filter(BalanceHistory.user_id == user_id).order_by(
            BalanceHistory.created_at.desc(), BalanceHistory.id.desc()
        ).limit(limit).all()

    def create_withdrawal(self, **data) -> WithdrawalRequest:
        item = WithdrawalRequest(**data)
        self.db.add(item)
        self.db.flush()
        return item

    def get_withdrawal(self, withdrawal_id: int, *, for_update: bool = False) -> WithdrawalRequest | None:
        query = self.db.query(WithdrawalRequest).filter(WithdrawalRequest.id == withdrawal_id)
        if for_update:
            query = query.with_for_update()
        return query.first()

    def get_withdrawal_by_provider_id(self, provider_payout_id: str, *, for_update: bool = False) -> WithdrawalRequest | None:
        query = self.db.query(WithdrawalRequest).filter(WithdrawalRequest.provider_payout_id == provider_payout_id)
        if for_update:
            query = query.with_for_update()
        return query.first()

    def list_user_withdrawals(self, user_id: int) -> list[WithdrawalRequest]:
        return self.db.query(WithdrawalRequest).filter(WithdrawalRequest.user_id == user_id).order_by(
            WithdrawalRequest.created_at.desc(), WithdrawalRequest.id.desc()
        ).all()

    def list_withdrawals(self, status: str | None = None, limit: int = 200) -> list[WithdrawalRequest]:
        query = self.db.query(WithdrawalRequest)
        if status:
            query = query.filter(WithdrawalRequest.status == status)
        return query.order_by(WithdrawalRequest.created_at.asc()).limit(limit).all()
