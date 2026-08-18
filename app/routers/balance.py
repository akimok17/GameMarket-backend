from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_admin, get_current_user
from app.schemas import DepositCreate, DepositResponse, WithdrawalRequestCreate, WithdrawalResponse
from app.services.balance_service import BalanceService
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/balance", tags=["balance"])


@router.get("/config")
def payment_config(current_user=Depends(get_current_user)):
    # Authenticated endpoint: the response contains capabilities/limits only,
    # never provider credentials.
    return PaymentService.config()


@router.get("/me")
def my_balance(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return BalanceService(db).get_balance(current_user.id)


@router.get("/history")
def history(limit: int = Query(default=100, ge=1, le=500), current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return BalanceService(db).get_history(current_user.id, limit)


@router.post("/deposit", response_model=DepositResponse, status_code=201)
def create_deposit(data: DepositCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return PaymentService(db).create_deposit(current_user.id, data)


@router.get("/deposits", response_model=list[DepositResponse])
def my_deposits(limit: int = Query(default=30, ge=1, le=100), current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return PaymentService(db).list_deposits(current_user.id, limit=limit)


@router.post("/deposits/{deposit_id}/sync", response_model=DepositResponse)
def sync_deposit(deposit_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return PaymentService(db).sync_deposit(deposit_id, current_user.id)


@router.post("/dev-deposit")
def dev_deposit(
    amount: Decimal = Query(..., gt=0),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return BalanceService(db).dev_deposit(current_user.id, amount)


@router.get("/sbp-banks")
def sbp_banks(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return BalanceService(db).list_sbp_banks()


@router.post("/withdraw", response_model=WithdrawalResponse, status_code=201)
def withdraw(data: WithdrawalRequestCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return BalanceService(db).request_withdrawal(current_user.id, data)


@router.get("/withdrawals", response_model=list[WithdrawalResponse])
def my_withdrawals(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return BalanceService(db).list_withdrawals(current_user.id)


@router.post("/withdrawals/{withdrawal_id}/sync", response_model=WithdrawalResponse)
def sync_withdrawal(withdrawal_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return BalanceService(db).sync_withdrawal(withdrawal_id, user_id=current_user.id)


@router.post("/admin/withdrawals/{withdrawal_id}/approve", response_model=WithdrawalResponse)
def approve_withdrawal(withdrawal_id: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    return BalanceService(db).resolve_withdrawal(withdrawal_id, admin.id, True)


@router.post("/admin/withdrawals/{withdrawal_id}/reject", response_model=WithdrawalResponse)
def reject_withdrawal(withdrawal_id: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    return BalanceService(db).resolve_withdrawal(withdrawal_id, admin.id, False)
