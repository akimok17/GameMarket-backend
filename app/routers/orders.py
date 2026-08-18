from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_admin, get_current_seller, get_current_user
from app.realtime import order_connections
from app.schemas import OrderCreate, OrderResponse
from app.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/", response_model=OrderResponse, status_code=201)
def create_order(data: OrderCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return OrderService(db).create(current_user.id, data)


@router.get("/my/buyer", response_model=list[OrderResponse])
def my_buyer_orders(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return OrderService(db).buyer_orders(current_user.id)


@router.get("/my/seller", response_model=list[OrderResponse])
def my_seller_orders(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return OrderService(db).seller_orders(current_user.id)


@router.post("/admin/auto-complete")
def auto_complete(_admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    return OrderService(db).auto_complete()


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    order = OrderService(db).get_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if current_user.id not in {order.buyer_id, order.seller_id} and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Access denied")
    return order


@router.post("/{order_id}/pay", response_model=OrderResponse)
async def pay_order(order_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    result = OrderService(db).pay(order_id, current_user.id)
    await order_connections.broadcast(order_id, {"type": "order_updated", "status": result.status, "reason": "paid"})
    return result


@router.put("/{order_id}/deliver", response_model=OrderResponse)
async def deliver_order(
    order_id: int,
    delivery_info: str = Body(..., embed=True, min_length=1, max_length=20000),
    seller=Depends(get_current_seller),
    db: Session = Depends(get_db),
):
    result = OrderService(db).deliver(order_id, seller.id, delivery_info)
    await order_connections.broadcast(order_id, {"type": "order_updated", "status": result.status, "reason": "delivered"})
    return result


@router.put("/{order_id}/confirm", response_model=OrderResponse)
async def confirm_order(order_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    result = OrderService(db).confirm(order_id, current_user.id)
    await order_connections.broadcast(order_id, {"type": "order_updated", "status": result.status, "reason": "confirmed"})
    return result


@router.delete("/{order_id}")
async def cancel_order(order_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    result = OrderService(db).cancel_pending(order_id, current_user.id)
    await order_connections.broadcast(order_id, {"type": "order_updated", "status": "cancelled", "reason": "cancelled"})
    return result
