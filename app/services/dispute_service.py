from datetime import datetime, timezone
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.models import Dispute
from app.repositories.balance_repository import BalanceRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.order_room_repository import OrderRoomRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.user_repository import UserRepository
from app.schemas import DisputeCreate
from app.services.notification_service import NotificationService


class DisputeService:
    def __init__(self, db: Session):
        self.db = db
        self.orders = OrderRepository(db)
        self.users = UserRepository(db)
        self.products = ProductRepository(db)
        self.balance = BalanceRepository(db)
        self.notifications = NotificationService(db)
        self.room = OrderRoomRepository(db)

    def create(self, initiator_id: int, data: DisputeCreate):
        order = self.orders.get_by_id(data.order_id, for_update=True)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        if initiator_id not in {order.buyer_id, order.seller_id}:
            raise HTTPException(status_code=403, detail="Access denied")
        if order.status not in {"paid", "delivered"} or order.settled_at is not None:
            raise HTTPException(status_code=409, detail="This order cannot be disputed")
        existing = self.db.query(Dispute).filter(Dispute.order_id == order.id, Dispute.status == "open").first()
        if existing:
            raise HTTPException(status_code=409, detail="An open dispute already exists")
        dispute = Dispute(
            order_id=order.id,
            initiator_id=initiator_id,
            reason=data.reason.strip(),
            description=data.description.strip() if data.description else None,
            status="open",
            previous_order_status=order.status,
        )
        self.db.add(dispute)
        order.status = "disputed"
        order.auto_complete_at = None
        order.last_activity_at = datetime.now(timezone.utc)
        self.room.add_event(order.id, "disputed", f"Открыт спор: {data.reason.strip()}", actor_id=initiator_id, payload={"reason": data.reason.strip()})
        other_user_id = order.seller_id if initiator_id == order.buyer_id else order.buyer_id
        self.notifications.create(other_user_id, "Открыт спор", f"По заказу #{order.id} открыт спор.", type="dispute", link=f"/order/{order.id}")
        self.db.commit()
        self.db.refresh(dispute)
        return dispute

    def get_for_user(self, dispute_id: int, user_id: int, is_admin: bool = False):
        dispute = self.db.query(Dispute).filter(Dispute.id == dispute_id).first()
        if not dispute:
            raise HTTPException(status_code=404, detail="Dispute not found")
        order = self.orders.get_by_id(dispute.order_id)
        if not is_admin and user_id not in {order.buyer_id, order.seller_id}:
            raise HTTPException(status_code=403, detail="Access denied")
        return dispute

    def get_by_order(self, order_id: int, user_id: int, is_admin: bool = False):
        order = self.orders.get_by_id(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        if not is_admin and user_id not in {order.buyer_id, order.seller_id}:
            raise HTTPException(status_code=403, detail="Access denied")
        return self.db.query(Dispute).filter(Dispute.order_id == order_id).order_by(Dispute.created_at.desc()).all()

    def get_by_user(self, user_id: int):
        order_ids = {o.id for o in self.orders.get_by_buyer(user_id)} | {o.id for o in self.orders.get_by_seller(user_id)}
        if not order_ids:
            return []
        return self.db.query(Dispute).filter(Dispute.order_id.in_(order_ids)).order_by(Dispute.created_at.desc()).all()

    def resolve(self, dispute_id: int, resolution: str, admin_id: int):
        now = datetime.now(timezone.utc)
        dispute = self.db.query(Dispute).filter(Dispute.id == dispute_id).with_for_update().first()
        if not dispute:
            raise HTTPException(status_code=404, detail="Dispute not found")
        if dispute.status != "open":
            raise HTTPException(status_code=409, detail="Dispute already resolved")
        order = self.orders.get_by_id(dispute.order_id, for_update=True)
        if not order or order.status != "disputed" or order.settled_at is not None:
            raise HTTPException(status_code=409, detail="Order settlement state is inconsistent")

        total = Decimal(order.total_price)
        if resolution == "buyer":
            buyer = self.users.get_by_id(order.buyer_id, for_update=True)
            buyer.balance = Decimal(buyer.balance or 0) + total
            restored = Decimal(getattr(order, "buyer_withdrawable_spent", 0) or 0)
            buyer.withdrawable_balance = Decimal(getattr(buyer, "withdrawable_balance", 0) or 0) + restored
            self.balance.add_history(buyer.id, total, "refund", f"Dispute #{dispute.id}: buyer refund", "dispute", dispute.id)
            if dispute.previous_order_status == "paid":
                product = self.products.get_by_id(order.product_id, for_update=True)
                if product:
                    product.stock_quantity += order.quantity
            order.status = "cancelled"
            order.cancelled_at = now
        elif resolution == "seller":
            seller = self.users.get_by_id(order.seller_id, for_update=True)
            earnings = Decimal(order.seller_earnings)
            seller.balance = Decimal(seller.balance or 0) + earnings
            seller.withdrawable_balance = Decimal(getattr(seller, "withdrawable_balance", 0) or 0) + earnings
            seller.total_sales = (seller.total_sales or 0) + 1
            self.balance.add_history(seller.id, earnings, "earning", f"Dispute #{dispute.id}: seller payout", "dispute", dispute.id)
            order.status = "completed"
            order.completed_at = now
        elif resolution == "split":
            if dispute.previous_order_status == "paid":
                product = self.products.get_by_id(order.product_id, for_update=True)
                if product:
                    product.stock_quantity += order.quantity
            buyer = self.users.get_by_id(order.buyer_id, for_update=True)
            seller = self.users.get_by_id(order.seller_id, for_update=True)
            seller_part = (total / Decimal("2")).quantize(Decimal("0.01"))
            buyer_part = total - seller_part
            buyer.balance = Decimal(buyer.balance or 0) + buyer_part
            seller.balance = Decimal(seller.balance or 0) + seller_part
            original_withdrawable = Decimal(getattr(order, "buyer_withdrawable_spent", 0) or 0)
            restored = (original_withdrawable * buyer_part / total).quantize(Decimal("0.01")) if total else Decimal("0")
            buyer.withdrawable_balance = Decimal(getattr(buyer, "withdrawable_balance", 0) or 0) + restored
            seller.withdrawable_balance = Decimal(getattr(seller, "withdrawable_balance", 0) or 0) + seller_part
            seller.total_sales = (seller.total_sales or 0) + 1
            self.balance.add_history(buyer.id, buyer_part, "refund", f"Dispute #{dispute.id}: split refund", "dispute", dispute.id)
            self.balance.add_history(seller.id, seller_part, "earning", f"Dispute #{dispute.id}: split payout", "dispute", dispute.id)
            order.status = "completed"
            order.completed_at = now
        else:
            raise HTTPException(status_code=400, detail="Invalid resolution")

        order.settled_at = now
        order.auto_complete_at = None
        order.last_activity_at = now
        dispute.status = "resolved"
        dispute.resolution = resolution
        dispute.resolved_at = now
        dispute.resolved_by = admin_id
        resolution_text = {"buyer": "Деньги возвращены покупателю", "seller": "Средства выплачены продавцу", "split": "Сумма разделена между сторонами"}[resolution]
        self.room.add_event(order.id, "dispute_resolved", f"Поддержка разрешила спор. {resolution_text}.", actor_id=admin_id, payload={"resolution": resolution})
        self.notifications.create(order.buyer_id, "Спор решён", f"Спор #{dispute.id} по заказу #{order.id} завершён: {resolution}.", type="dispute", link=f"/order/{order.id}")
        self.notifications.create(order.seller_id, "Спор решён", f"Спор #{dispute.id} по заказу #{order.id} завершён: {resolution}.", type="dispute", link=f"/order/{order.id}")
        self.db.commit()
        self.db.refresh(dispute)
        return dispute
