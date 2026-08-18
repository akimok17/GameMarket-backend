from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.yookassa import YooKassaClient, YooKassaError
from app.repositories.balance_repository import BalanceRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.user_repository import UserRepository
from app.schemas import DepositCreate

CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


class PaymentService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = PaymentRepository(db)
        self.users = UserRepository(db)
        self.balance = BalanceRepository(db)
        self.provider = YooKassaClient()

    @staticmethod
    def config() -> dict:
        return {
            "payment_provider": settings.PAYMENT_PROVIDER,
            "payment_configured": settings.payment_provider_configured,
            "payout_provider": settings.PAYOUT_PROVIDER,
            "payout_configured": settings.payout_provider_configured,
            "dev_deposit_available": settings.ENVIRONMENT != "production" and settings.ALLOW_DEV_DEPOSITS,
            "deposit_min": settings.DEPOSIT_MIN_RUB,
            "deposit_max": settings.DEPOSIT_MAX_RUB,
            "withdrawal_min": settings.WITHDRAWAL_MIN_RUB,
            "withdrawal_max": settings.WITHDRAWAL_MAX_RUB,
            "withdrawal_methods": ["sbp"] if settings.PAYOUT_PROVIDER == "yookassa" else (["manual"] if settings.PAYOUT_PROVIDER == "manual" else []),
        }

    def _validate_deposit_amount(self, amount: Decimal) -> Decimal:
        value = money(amount)
        if value < settings.DEPOSIT_MIN_RUB or value > settings.DEPOSIT_MAX_RUB:
            raise HTTPException(
                status_code=400,
                detail=f"Deposit amount must be between {settings.DEPOSIT_MIN_RUB} and {settings.DEPOSIT_MAX_RUB} RUB",
            )
        return value

    def create_deposit(self, user_id: int, data: DepositCreate):
        if settings.PAYMENT_PROVIDER != "yookassa" or not settings.payment_provider_configured:
            raise HTTPException(status_code=503, detail="Real balance top-up is not configured")
        if not self.users.get_by_id(user_id):
            raise HTTPException(status_code=404, detail="User not found")

        amount = self._validate_deposit_amount(data.amount)
        key = data.idempotency_key or uuid4().hex
        existing = self.repo.get_by_idempotency_key(key)
        if existing:
            if existing.user_id != user_id or money(existing.amount) != amount:
                raise HTTPException(status_code=409, detail="Idempotency key is already used by another deposit")
            if existing.provider_payment_id or existing.status in {"succeeded", "canceled"}:
                return existing
            deposit = existing
        else:
            deposit = self.repo.create_deposit(
                user_id=user_id,
                provider="yookassa",
                idempotency_key=key,
                amount=amount,
                currency="RUB",
                status="pending",
            )
            self.db.commit()
            self.db.refresh(deposit)

        if data.platform == "android":
            # YooKassa redirect return_url is a web URL. Return to a small HTTPS
            # bridge page which can deep-link back into the Android app. The app
            # also keeps the deposit id locally and syncs on resume as a fallback.
            base_return = settings.ANDROID_PAYMENT_RETURN_URL or f"{settings.PUBLIC_APP_URL}/payment-return"
            parts = urlsplit(base_return)
            query = dict(parse_qsl(parts.query, keep_blank_values=True))
            query["deposit_id"] = str(deposit.id)
            return_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
        else:
            return_url = settings.YOOKASSA_RETURN_URL or (
                f"{settings.PUBLIC_APP_URL}/profile?payment_return=1&deposit_id={deposit.id}"
            )
        try:
            provider_payment = self.provider.create_payment(
                amount=amount,
                deposit_id=deposit.id,
                idempotency_key=key,
                return_url=return_url,
            )
        except YooKassaError as exc:
            current = self.repo.get_deposit(deposit.id, for_update=True)
            current.failure_reason = str(exc)[:1000]
            self.db.commit()
            raise HTTPException(status_code=502, detail="Не удалось создать платеж. Повторите попытку позже.") from exc

        current = self.repo.get_deposit(deposit.id, for_update=True)
        current.provider_payment_id = str(provider_payment.get("id") or "") or None
        confirmation = provider_payment.get("confirmation") if isinstance(provider_payment.get("confirmation"), dict) else {}
        current.confirmation_url = confirmation.get("confirmation_url")
        current.failure_reason = None
        provider_status = str(provider_payment.get("status") or "pending")
        if provider_status == "canceled":
            current.status = "canceled"
            current.canceled_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(current)
        return current

    def list_deposits(self, user_id: int, limit: int = 50):
        return self.repo.list_user_deposits(user_id, limit=limit)

    def get_deposit_for_user(self, deposit_id: int, user_id: int):
        item = self.repo.get_deposit(deposit_id)
        if not item or item.user_id != user_id:
            raise HTTPException(status_code=404, detail="Deposit not found")
        return item

    def sync_deposit(self, deposit_id: int, user_id: int):
        item = self.get_deposit_for_user(deposit_id, user_id)
        if not item.provider_payment_id or item.provider != "yookassa":
            return item
        try:
            provider_payment = self.provider.get_payment(item.provider_payment_id)
        except YooKassaError as exc:
            raise HTTPException(status_code=502, detail="Не удалось проверить статус платежа") from exc
        self._apply_payment(provider_payment, expected_deposit_id=item.id)
        return self.get_deposit_for_user(deposit_id, user_id)

    @staticmethod
    def _provider_amount(obj: dict) -> tuple[Decimal, str]:
        amount = obj.get("amount") if isinstance(obj.get("amount"), dict) else {}
        try:
            value = money(Decimal(str(amount.get("value"))))
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid provider amount") from exc
        return value, str(amount.get("currency") or "")

    def _resolve_deposit(self, provider_payment: dict, expected_deposit_id: int | None = None):
        provider_id = str(provider_payment.get("id") or "")
        metadata = provider_payment.get("metadata") if isinstance(provider_payment.get("metadata"), dict) else {}
        raw_deposit_id = metadata.get("deposit_id")
        try:
            metadata_deposit_id = int(raw_deposit_id) if raw_deposit_id is not None else None
        except (TypeError, ValueError):
            metadata_deposit_id = None

        if expected_deposit_id is not None and metadata_deposit_id not in {None, expected_deposit_id}:
            raise HTTPException(status_code=409, detail="Payment metadata mismatch")

        item = self.repo.get_by_provider_payment_id(provider_id, for_update=True) if provider_id else None
        if not item and metadata_deposit_id:
            item = self.repo.get_deposit(metadata_deposit_id, for_update=True)
        if not item:
            raise HTTPException(status_code=404, detail="Deposit not found")
        if expected_deposit_id is not None and item.id != expected_deposit_id:
            raise HTTPException(status_code=409, detail="Payment does not match deposit")
        if provider_id and item.provider_payment_id and item.provider_payment_id != provider_id:
            raise HTTPException(status_code=409, detail="Provider payment mismatch")
        if provider_id and not item.provider_payment_id:
            item.provider_payment_id = provider_id
        return item

    def _apply_payment(self, provider_payment: dict, expected_deposit_id: int | None = None) -> None:
        item = self._resolve_deposit(provider_payment, expected_deposit_id=expected_deposit_id)
        provider_amount, currency = self._provider_amount(provider_payment)
        if currency != item.currency or provider_amount != money(item.amount):
            self.db.rollback()
            raise HTTPException(status_code=409, detail="Payment amount mismatch")

        status = str(provider_payment.get("status") or "")
        now = datetime.now(timezone.utc)
        if status == "succeeded":
            if provider_payment.get("paid") is not True:
                self.db.rollback()
                raise HTTPException(status_code=409, detail="Payment is not marked as paid")
            if item.status != "succeeded":
                user = self.users.get_by_id(item.user_id, for_update=True)
                if not user:
                    self.db.rollback()
                    raise HTTPException(status_code=404, detail="User not found")
                user.balance = money(Decimal(user.balance or 0) + provider_amount)
                item.status = "succeeded"
                item.succeeded_at = now
                item.canceled_at = None
                item.failure_reason = None
                self.balance.add_history(
                    user.id,
                    provider_amount,
                    "deposit",
                    f"Пополнение баланса #{item.id}",
                    "deposit",
                    item.id,
                )
        elif status == "canceled" and item.status != "succeeded":
            item.status = "canceled"
            item.canceled_at = now
            details = provider_payment.get("cancellation_details") if isinstance(provider_payment.get("cancellation_details"), dict) else {}
            item.failure_reason = str(details.get("reason") or "Payment canceled")[:1000]
        self.db.commit()

    def handle_yookassa_webhook(self, payload: dict) -> dict:
        event = str(payload.get("event") or "")
        obj = payload.get("object") if isinstance(payload.get("object"), dict) else {}
        if event not in {"payment.succeeded", "payment.canceled"}:
            return {"ok": True, "ignored": True}
        payment_id = str(obj.get("id") or "")
        if not payment_id:
            raise HTTPException(status_code=400, detail="Missing payment id")

        # Do not turn this public endpoint into a proxy for arbitrary provider lookups.
        # Unknown IDs are rejected locally; YooKassa will retry legitimate events if
        # an extremely fast webhook races the initial provider-id persistence.
        if not self.repo.get_by_provider_payment_id(payment_id):
            raise HTTPException(status_code=404, detail="Unknown payment")

        # Provider webhooks are not trusted as the financial source of truth. Re-fetch
        # the object from YooKassa before changing any balance.
        try:
            authoritative = self.provider.get_payment(payment_id)
        except YooKassaError as exc:
            raise HTTPException(status_code=502, detail="Unable to verify payment webhook") from exc
        self._apply_payment(authoritative)
        return {"ok": True}
