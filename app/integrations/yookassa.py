from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx

from app.core.config import settings


class YooKassaError(RuntimeError):
    """A sanitized provider error safe to surface through the service layer."""

    def __init__(self, message: str, *, status_code: int | None = None, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


class YooKassaClient:
    API_BASE = "https://api.yookassa.ru/v3"

    def _credentials(self, *, payout: bool = False) -> tuple[str, str]:
        if payout:
            login = settings.YOOKASSA_PAYOUT_GATEWAY_ID
            password = settings.YOOKASSA_PAYOUT_SECRET_KEY
        else:
            login = settings.YOOKASSA_SHOP_ID
            password = settings.YOOKASSA_SECRET_KEY
        if not login or not password:
            raise YooKassaError("YooKassa credentials are not configured")
        return login, password

    def _request(
        self,
        method: str,
        path: str,
        *,
        payout: bool = False,
        json: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        login, password = self._credentials(payout=payout)
        headers = {"Accept": "application/json"}
        if idempotency_key:
            headers["Idempotence-Key"] = idempotency_key
        try:
            response = httpx.request(
                method,
                self.API_BASE + path,
                auth=(login, password),
                headers=headers,
                json=json,
                timeout=settings.PAYMENT_TIMEOUT_SECONDS,
            )
        except httpx.RequestError as exc:
            raise YooKassaError("Payment provider is temporarily unavailable") from exc

        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code >= 400:
            description = str(payload.get("description") or payload.get("code") or "Provider request failed")
            raise YooKassaError(description, status_code=response.status_code, payload=payload)
        if not isinstance(payload, dict):
            raise YooKassaError("Unexpected response from payment provider")
        return payload

    @staticmethod
    def _amount(value: Decimal) -> dict[str, str]:
        return {"value": f"{Decimal(value):.2f}", "currency": "RUB"}

    def create_payment(self, *, amount: Decimal, deposit_id: int, idempotency_key: str, return_url: str) -> dict[str, Any]:
        body = {
            "amount": self._amount(amount),
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": f"Пополнение баланса GameMarket #{deposit_id}",
            "metadata": {"deposit_id": str(deposit_id)},
        }
        return self._request("POST", "/payments", json=body, idempotency_key=idempotency_key)

    def get_payment(self, payment_id: str) -> dict[str, Any]:
        return self._request("GET", f"/payments/{payment_id}")

    def list_sbp_banks(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/sbp_banks", payout=True)
        items = payload.get("items") or []
        return [x for x in items if isinstance(x, dict)]

    def create_sbp_payout(
        self,
        *,
        amount: Decimal,
        phone: str,
        bank_id: str,
        withdrawal_id: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        digits = "".join(ch for ch in phone if ch.isdigit())
        body = {
            "amount": self._amount(amount),
            "payout_destination_data": {
                "type": "sbp",
                "phone": digits,
                "bank_id": bank_id,
            },
            "description": f"Вывод GameMarket #{withdrawal_id}",
            "metadata": {"withdrawal_id": str(withdrawal_id)},
        }
        return self._request("POST", "/payouts", payout=True, json=body, idempotency_key=idempotency_key)

    def get_payout(self, payout_id: str) -> dict[str, Any]:
        return self._request("GET", f"/payouts/{payout_id}", payout=True)
