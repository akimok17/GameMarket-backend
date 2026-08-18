from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_admin
from app.models.models import Dispute, Order, Product, SupportTicket, User, WithdrawalRequest
from app.services.balance_service import BalanceService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview")
def overview(_admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    return {
        "users": db.query(func.count(User.id)).scalar() or 0,
        "sellers": db.query(func.count(User.id)).filter(User.is_seller.is_(True)).scalar() or 0,
        "active_products": db.query(func.count(Product.id)).filter(Product.status == "active").scalar() or 0,
        "orders": db.query(func.count(Order.id)).scalar() or 0,
        "open_disputes": db.query(func.count(Dispute.id)).filter(Dispute.status == "open").scalar() or 0,
        "pending_withdrawals": db.query(func.count(WithdrawalRequest.id)).filter(WithdrawalRequest.status == "pending").scalar() or 0,
        "open_support_tickets": db.query(func.count(SupportTicket.id)).filter(SupportTicket.status != "closed").scalar() or 0,
    }


@router.get("/users")
def users(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), _admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    items = db.query(User).order_by(User.created_at.desc()).offset(skip).limit(limit).all()
    return [{"id":x.id,"username":x.username,"email":x.email,"is_seller":x.is_seller,"is_admin":x.is_admin,"is_active":x.is_active,"balance":x.balance,"created_at":x.created_at} for x in items]


@router.put("/users/{user_id}/active")
def set_user_active(user_id: int, active: bool, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    if user_id == admin.id and not active:
        raise HTTPException(status_code=400, detail="Cannot disable your own admin account")
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = active
    db.commit()
    return {"id": user.id, "is_active": user.is_active}


@router.put("/products/{product_id}/verified")
def set_product_verified(product_id: int, verified: bool, _admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).with_for_update().first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_verified = verified
    db.commit()
    return {"id": product.id, "is_verified": product.is_verified}


@router.get("/disputes")
def disputes(status: str = "open", _admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    return db.query(Dispute).filter(Dispute.status == status).order_by(Dispute.created_at.asc()).all()


@router.get("/withdrawals")
def withdrawals(status: str = "pending", _admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    return BalanceService(db).admin_list_withdrawals(status=status)
