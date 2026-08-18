from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decrypt_content, encrypt_content
from app.core.verification_policy import policy_satisfied, policy_text
from app.integrations.yookassa import YooKassaClient, YooKassaError
from app.repositories.balance_repository import BalanceRepository
from app.repositories.user_repository import UserRepository
from app.schemas import WithdrawalRequestCreate

CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


class BalanceService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = BalanceRepository(db)
        self.user_repo = UserRepository(db)
        self.provider = YooKassaClient()

    @staticmethod
    def _normalize_phone(value: str) -> str:
        raw = str(value or "").strip()
        digits = re.sub(r"\D", "", raw)
        if digits.startswith("8") and len(digits) == 11:
            digits = "7" + digits[1:]
        if not digits.startswith("7") or len(digits) != 11:
            raise HTTPException(status_code=400, detail="Для выплаты по СБП нужен российский номер в формате +7XXXXXXXXXX")
        return "+" + digits

    @staticmethod
    def _protect_destination(value: str) -> str:
        return "enc:" + encrypt_content(value.strip())

    @staticmethod
    def _reveal_destination(value: str) -> str:
        value = str(value or "")
        if value.startswith("enc:"):
            try:
                return decrypt_content(value[4:])
            except Exception:
                raise HTTPException(status_code=500, detail="Withdrawal destination cannot be decrypted")
        return value

    @staticmethod
    def _mask_destination(value: str, wallet_type: str) -> str:
        if wallet_type == "sbp":
            digits = re.sub(r"\D", "", value)
            if len(digits) >= 4:
                return "+7 *** ***-**-" + digits[-2:]
        if len(value) <= 6:
            return "***"
        return value[:2] + "***" + value[-4:]

    def _serialize_withdrawal(self, req, *, reveal_destination: bool = False) -> dict:
        raw = self._reveal_destination(req.wallet_address)
        return {
            "id": req.id,
            "user_id": req.user_id,
            "amount": req.amount,
            "wallet_type": req.wallet_type,
            "wallet_address": raw if reveal_destination else self._mask_destination(raw, req.wallet_type),
            "bank_id": req.bank_id,
            "provider": req.provider or "manual",
            "provider_payout_id": req.provider_payout_id,
            "failure_reason": req.failure_reason,
            "status": req.status,
            "created_at": req.created_at,
            "processed_at": req.processed_at,
        }

    def get_balance(self, user_id: int):
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        balance = money(Decimal(user.balance or 0))
        frozen = money(Decimal(user.balance_frozen or 0))
        withdrawable = money(Decimal(getattr(user, "withdrawable_balance", 0) or 0))
        available = max(Decimal("0"), money(balance - frozen))
        return {
            "balance": balance,
            "frozen": frozen,
            "available": available,
            "withdrawable": withdrawable,
            "withdrawable_available": max(Decimal("0"), min(withdrawable, available)),
        }

    def get_history(self, user_id: int, limit: int = 100):
        if not self.user_repo.get_by_id(user_id):
            raise HTTPException(status_code=404, detail="User not found")
        return self.repo.get_history(user_id, limit=limit)

    def dev_deposit(self, user_id: int, amount: Decimal):
        if settings.ENVIRONMENT == "production" or not settings.ALLOW_DEV_DEPOSITS:
            raise HTTPException(status_code=403, detail="Development deposits are disabled. Configure a real payment provider.")
        amount = money(amount)
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")
        user = self.user_repo.get_by_id(user_id, for_update=True)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.balance = money(Decimal(user.balance or 0) + amount)
        # Development/real top-ups are spendable but are not seller earnings,
        # therefore they are intentionally not withdrawable.
        self.repo.add_history(user_id, amount, "dev_deposit", "Development balance top-up")
        self.db.commit()
        return self.get_balance(user_id)

    def request_withdrawal(self, user_id: int, data: WithdrawalRequestCreate):
        user = self.user_repo.get_by_id(user_id, for_update=True)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        withdrawal_policy = settings.WITHDRAWAL_VERIFICATION_POLICY if settings.REQUIRE_VERIFIED_FOR_WITHDRAWAL else "none"
        if not policy_satisfied(user, withdrawal_policy):
            raise HTTPException(status_code=403, detail=policy_text(withdrawal_policy))

        amount = money(data.amount)
        if amount < settings.WITHDRAWAL_MIN_RUB or amount > settings.WITHDRAWAL_MAX_RUB:
            raise HTTPException(
                status_code=400,
                detail=f"Withdrawal amount must be between {settings.WITHDRAWAL_MIN_RUB} and {settings.WITHDRAWAL_MAX_RUB} RUB",
            )

        balance = money(Decimal(user.balance or 0))
        frozen = money(Decimal(user.balance_frozen or 0))
        withdrawable = money(Decimal(getattr(user, "withdrawable_balance", 0) or 0))
        withdrawable_available = min(withdrawable, balance - frozen)
        if amount > withdrawable_available:
            raise HTTPException(status_code=400, detail="Недостаточно средств, доступных для вывода. Выводить можно только заработок продавца.")

        wallet_type = data.wallet_type.strip().lower()
        provider = settings.PAYOUT_PROVIDER
        destination = data.wallet_address.strip()
        bank_id = data.bank_id.strip() if data.bank_id else None

        if provider == "none":
            raise HTTPException(status_code=503, detail="Withdrawals are temporarily disabled")
        if provider == "yookassa":
            if not settings.payout_provider_configured:
                raise HTTPException(status_code=503, detail="YooKassa payouts are not configured")
            if wallet_type != "sbp":
                raise HTTPException(status_code=400, detail="For automatic payouts only SBP is supported")
            if not user.phone_verified_at or not user.phone:
                raise HTTPException(status_code=403, detail="Подтвердите номер телефона перед выводом по СБП")
            destination = self._normalize_phone(destination)
            verified_phone = self._normalize_phone(user.phone)
            if destination != verified_phone:
                raise HTTPException(status_code=400, detail="Вывод по СБП разрешён только на подтверждённый номер аккаунта")
            if not bank_id:
                raise HTTPException(status_code=400, detail="Выберите банк СБП")
        else:
            provider = "manual"
            if wallet_type == "sbp":
                destination = self._normalize_phone(destination)

        user.balance_frozen = money(frozen + amount)
        req = self.repo.create_withdrawal(
            user_id=user_id,
            amount=amount,
            wallet_type=wallet_type,
            wallet_address=self._protect_destination(destination),
            bank_id=bank_id,
            provider=provider,
            idempotency_key=uuid4().hex,
            status="pending",
        )
        self.repo.add_history(user_id, Decimal("0"), "withdrawal_hold", f"Withdrawal #{req.id} reserved", "withdrawal", req.id)
        self.db.commit()
        self.db.refresh(req)
        return self._serialize_withdrawal(req)

    def list_withdrawals(self, user_id: int):
        return [self._serialize_withdrawal(x) for x in self.repo.list_user_withdrawals(user_id)]

    def admin_list_withdrawals(self, status: str | None = "pending"):
        # Administrators need the actual destination for manual payouts; it remains encrypted at rest.
        return [self._serialize_withdrawal(x, reveal_destination=True) for x in self.repo.list_withdrawals(status=status)]

    def list_sbp_banks(self):
        if settings.PAYOUT_PROVIDER != "yookassa" or not settings.payout_provider_configured:
            raise HTTPException(status_code=503, detail="SBP payouts are not configured")
        try:
            items = self.provider.list_sbp_banks()
        except YooKassaError as exc:
            raise HTTPException(status_code=502, detail="Не удалось загрузить список банков СБП") from exc
        result = [
            {"bank_id": str(x.get("bank_id") or ""), "name": str(x.get("name") or "")}
            for x in items
            if x.get("bank_id") and x.get("name")
        ]
        return sorted(result, key=lambda x: x["name"].lower())

    def _finalize_manual(self, req, admin_id: int):
        user = self.user_repo.get_by_id(req.user_id, for_update=True)
        amount = money(req.amount)
        frozen = money(Decimal(user.balance_frozen or 0))
        balance = money(Decimal(user.balance or 0))
        withdrawable = money(Decimal(user.withdrawable_balance or 0))
        if frozen < amount or balance < amount or withdrawable < amount:
            raise HTTPException(status_code=409, detail="Balance is inconsistent")
        user.balance_frozen = money(frozen - amount)
        user.balance = money(balance - amount)
        user.withdrawable_balance = money(withdrawable - amount)
        req.status = "succeeded"
        req.processed_at = datetime.now(timezone.utc)
        req.processed_by = admin_id
        self.repo.add_history(user.id, -amount, "withdrawal", f"Withdrawal #{req.id} completed", "withdrawal", req.id)
        self.db.commit()
        self.db.refresh(req)
        return self._serialize_withdrawal(req)

    def _release_withdrawal(self, req, *, status: str, reason: str | None = None):
        if req.status in {"canceled", "rejected"}:
            return
        user = self.user_repo.get_by_id(req.user_id, for_update=True)
        amount = money(req.amount)
        frozen = money(Decimal(user.balance_frozen or 0))
        if frozen < amount:
            raise HTTPException(status_code=409, detail="Frozen balance is inconsistent")
        user.balance_frozen = money(frozen - amount)
        req.status = status
        req.failure_reason = reason[:1000] if reason else None
        req.processed_at = datetime.now(timezone.utc)
        self.repo.add_history(user.id, Decimal("0"), "withdrawal_release", f"Withdrawal #{req.id} released", "withdrawal", req.id)

    def _apply_provider_payout(self, provider_payout: dict, *, expected_withdrawal_id: int | None = None):
        payout_id = str(provider_payout.get("id") or "")
        metadata = provider_payout.get("metadata") if isinstance(provider_payout.get("metadata"), dict) else {}
        try:
            meta_id = int(metadata.get("withdrawal_id")) if metadata.get("withdrawal_id") is not None else None
        except (TypeError, ValueError):
            meta_id = None
        if expected_withdrawal_id is not None and meta_id not in {None, expected_withdrawal_id}:
            raise HTTPException(status_code=409, detail="Payout metadata mismatch")

        req = self.repo.get_withdrawal_by_provider_id(payout_id, for_update=True) if payout_id else None
        if not req and meta_id:
            req = self.repo.get_withdrawal(meta_id, for_update=True)
        if not req:
            raise HTTPException(status_code=404, detail="Withdrawal not found")
        if expected_withdrawal_id is not None and req.id != expected_withdrawal_id:
            raise HTTPException(status_code=409, detail="Payout does not match withdrawal")
        if payout_id and req.provider_payout_id and req.provider_payout_id != payout_id:
            raise HTTPException(status_code=409, detail="Provider payout mismatch")
        if payout_id and not req.provider_payout_id:
            req.provider_payout_id = payout_id

        amount_obj = provider_payout.get("amount") if isinstance(provider_payout.get("amount"), dict) else {}
        try:
            provider_amount = money(Decimal(str(amount_obj.get("value"))))
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid payout amount") from exc
        if str(amount_obj.get("currency") or "") != "RUB" or provider_amount != money(req.amount):
            self.db.rollback()
            raise HTTPException(status_code=409, detail="Payout amount mismatch")

        status = str(provider_payout.get("status") or "")
        now = datetime.now(timezone.utc)
        if status == "succeeded" and req.status != "succeeded":
            user = self.user_repo.get_by_id(req.user_id, for_update=True)
            amount = money(req.amount)
            frozen = money(Decimal(user.balance_frozen or 0))
            balance = money(Decimal(user.balance or 0))
            withdrawable = money(Decimal(user.withdrawable_balance or 0))
            if frozen < amount or balance < amount or withdrawable < amount:
                self.db.rollback()
                raise HTTPException(status_code=409, detail="Balance is inconsistent")
            user.balance_frozen = money(frozen - amount)
            user.balance = money(balance - amount)
            user.withdrawable_balance = money(withdrawable - amount)
            req.status = "succeeded"
            req.processed_at = now
            req.failure_reason = None
            self.repo.add_history(user.id, -amount, "withdrawal", f"Withdrawal #{req.id} completed", "withdrawal", req.id)
        elif status == "canceled" and req.status != "succeeded":
            details = provider_payout.get("cancellation_details") if isinstance(provider_payout.get("cancellation_details"), dict) else {}
            self._release_withdrawal(req, status="canceled", reason=str(details.get("reason") or "Payout canceled"))
        else:
            if req.status == "pending":
                req.status = "processing"
        self.db.commit()
        return req

    def resolve_withdrawal(self, withdrawal_id: int, admin_id: int, approve: bool):
        req = self.repo.get_withdrawal(withdrawal_id, for_update=True)
        if not req:
            raise HTTPException(status_code=404, detail="Withdrawal request not found")
        if req.status not in {"pending", "processing"}:
            raise HTTPException(status_code=400, detail="Withdrawal already processed")

        if not approve:
            if req.status == "processing":
                raise HTTPException(status_code=409, detail="Processing payout cannot be rejected; sync its provider status first")
            req.processed_by = admin_id
            self._release_withdrawal(req, status="rejected", reason="Rejected by administrator")
            self.db.commit()
            self.db.refresh(req)
            return self._serialize_withdrawal(req)

        if (req.provider or "manual") != "yookassa":
            return self._finalize_manual(req, admin_id)

        if not settings.payout_provider_configured:
            raise HTTPException(status_code=503, detail="YooKassa payouts are not configured")

        # Mark processing before the external call. If the network dies after
        # YooKassa accepts the request, the same idempotency key can be retried.
        req.status = "processing"
        req.processed_by = admin_id
        req.failure_reason = None
        destination = self._reveal_destination(req.wallet_address)
        bank_id = req.bank_id
        idempotency_key = req.idempotency_key or uuid4().hex
        req.idempotency_key = idempotency_key
        self.db.commit()

        if req.provider_payout_id:
            try:
                provider_payout = self.provider.get_payout(req.provider_payout_id)
            except YooKassaError as exc:
                raise HTTPException(status_code=502, detail="Не удалось проверить статус выплаты") from exc
        else:
            try:
                provider_payout = self.provider.create_sbp_payout(
                    amount=money(req.amount),
                    phone=destination,
                    bank_id=bank_id,
                    withdrawal_id=req.id,
                    idempotency_key=idempotency_key,
                )
            except YooKassaError as exc:
                current = self.repo.get_withdrawal(req.id, for_update=True)
                current.failure_reason = str(exc)[:1000]
                self.db.commit()
                raise HTTPException(status_code=502, detail="Провайдер не подтвердил создание выплаты. Средства остаются зарезервированы.") from exc

        applied = self._apply_provider_payout(provider_payout, expected_withdrawal_id=req.id)
        return self._serialize_withdrawal(applied)

    def sync_withdrawal(self, withdrawal_id: int, user_id: int | None = None):
        req = self.repo.get_withdrawal(withdrawal_id)
        if not req or (user_id is not None and req.user_id != user_id):
            raise HTTPException(status_code=404, detail="Withdrawal not found")
        if (req.provider or "manual") != "yookassa" or not req.provider_payout_id:
            return self._serialize_withdrawal(req)
        try:
            provider_payout = self.provider.get_payout(req.provider_payout_id)
        except YooKassaError as exc:
            raise HTTPException(status_code=502, detail="Не удалось проверить статус выплаты") from exc
        applied = self._apply_provider_payout(provider_payout, expected_withdrawal_id=req.id)
        return self._serialize_withdrawal(applied)

    def handle_yookassa_payout_webhook(self, payload: dict):
        event = str(payload.get("event") or "")
        obj = payload.get("object") if isinstance(payload.get("object"), dict) else {}
        if event not in {"payout.succeeded", "payout.canceled"}:
            return {"ok": True, "ignored": True}
        payout_id = str(obj.get("id") or "")
        if not payout_id:
            raise HTTPException(status_code=400, detail="Missing payout id")
        if not self.repo.get_withdrawal_by_provider_id(payout_id):
            raise HTTPException(status_code=404, detail="Unknown payout")
        try:
            authoritative = self.provider.get_payout(payout_id)
        except YooKassaError as exc:
            raise HTTPException(status_code=502, detail="Unable to verify payout webhook") from exc
        self._apply_provider_payout(authoritative)
        return {"ok": True}
