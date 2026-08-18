from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.balance_service import BalanceService
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/yookassa/webhook")
def yookassa_webhook(payload: dict, db: Session = Depends(get_db)):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid webhook payload")

    event = str(payload.get("event") or "")
    if event.startswith("payment."):
        return PaymentService(db).handle_yookassa_webhook(payload)
    if event.startswith("payout."):
        return BalanceService(db).handle_yookassa_payout_webhook(payload)
    return {"ok": True, "ignored": True}
