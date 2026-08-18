from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decrypt_content, encrypt_content
from app.repositories.balance_repository import BalanceRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.order_room_repository import OrderRoomRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.user_repository import UserRepository
from app.schemas import OrderCreate
from app.services.notification_service import NotificationService

CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


class OrderService:
    def __init__(self, db: Session):
        self.db = db
        self.orders = OrderRepository(db)
        self.products = ProductRepository(db)
        self.users = UserRepository(db)
        self.balance = BalanceRepository(db)
        self.notifications = NotificationService(db)
        self.room = OrderRoomRepository(db)

    def create(self, buyer_id: int, data: OrderCreate):
        product = self.products.get_by_id(data.product_id)
        if not product or product.status != "active":
            raise HTTPException(status_code=404, detail="Product not available")
        if product.seller_id == buyer_id:
            raise HTTPException(status_code=400, detail="Cannot buy your own product")
        if product.stock_quantity < data.quantity:
            raise HTTPException(status_code=409, detail="Not enough stock")
        total = money(Decimal(product.price) * data.quantity)
        commission = money(total * settings.COMMISSION_RATE)
        earnings = money(total - commission)
        order = self.orders.create(
            buyer_id=buyer_id,
            seller_id=product.seller_id,
            product_id=product.id,
            product_title_snapshot=product.title,
            product_category_snapshot=product.category,
            quantity=data.quantity,
            total_price=total,
            commission=commission,
            seller_earnings=earnings,
            status="pending",
        )
        self.room.add_event(order.id, "created", "Заказ создан", actor_id=buyer_id, payload={"amount": str(total)})
        self.db.commit()
        self.db.refresh(order)
        return order

    def pay(self, order_id: int, buyer_id: int):
        now = datetime.now(timezone.utc)
        order = self.orders.get_by_id(order_id, for_update=True)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        if order.buyer_id != buyer_id:
            raise HTTPException(status_code=403, detail="Access denied")
        if order.status != "pending":
            raise HTTPException(status_code=409, detail="Order is not awaiting payment")

        buyer = self.users.get_by_id(buyer_id, for_update=True)
        product = self.products.get_by_id(order.product_id, for_update=True)
        if not buyer or not product or product.status != "active":
            raise HTTPException(status_code=409, detail="Product or buyer is unavailable")

        total = Decimal(order.total_price)
        available = Decimal(buyer.balance or 0) - Decimal(buyer.balance_frozen or 0)
        if available < total:
            raise HTTPException(status_code=400, detail="Insufficient balance")
        if product.stock_quantity < order.quantity:
            raise HTTPException(status_code=409, detail="Not enough stock")

        buyer.balance = Decimal(buyer.balance or 0) - total
        withdrawable_before = Decimal(getattr(buyer, "withdrawable_balance", 0) or 0)
        withdrawable_spent = min(withdrawable_before, total)
        buyer.withdrawable_balance = money(withdrawable_before - withdrawable_spent)
        order.buyer_withdrawable_spent = money(withdrawable_spent)
        product.stock_quantity -= order.quantity
        order.paid_at = now
        order.last_activity_at = now
        self.balance.add_history(buyer.id, -total, "payment", f"Payment for order #{order.id}", "order", order.id)
        self.room.add_event(order.id, "paid", f"Покупатель оплатил заказ. {total} ₽ помещены в резерв сделки.", actor_id=buyer_id, payload={"amount": str(total)})

        if product.fulfillment_type == "automatic":
            items = self.products.available_inventory(product.id, limit=order.quantity, for_update=True)
            if len(items) != order.quantity:
                self.db.rollback()
                raise HTTPException(status_code=409, detail="Automatic inventory is inconsistent")
            delivered = []
            for item in items:
                item.status = "sold"
                item.order_id = order.id
                item.sold_at = now
                delivered.append(decrypt_content(item.encrypted_content))
            order.delivery_secret = encrypt_content("\n".join(delivered))
            order.delivery_info = "Товар выдан автоматически"
            order.status = "delivered"
            order.delivered_at = now
            order.auto_complete_at = now + timedelta(hours=settings.AUTO_COMPLETE_HOURS)
            self.room.add_event(order.id, "delivered", "GameMarket автоматически выдал цифровой товар покупателю.", payload={"automatic": True})
        else:
            order.status = "paid"
            self.room.add_event(order.id, "awaiting_delivery", "Оплата подтверждена. Ожидается выполнение заказа продавцом.")

        self.notifications.create(
            order.seller_id,
            "Новый оплаченный заказ",
            f"Заказ #{order.id} оплачен покупателем.",
            type="order",
            link=f"/order/{order.id}",
        )
        if order.status == "delivered":
            self.notifications.create(
                order.buyer_id,
                "Товар выдан",
                f"Заказ #{order.id} выдан автоматически. Проверьте товар перед подтверждением.",
                type="order",
                link=f"/order/{order.id}",
            )

        self.db.commit()
        self.db.refresh(order)
        return order

    def deliver(self, order_id: int, seller_id: int, delivery_info: str):
        now = datetime.now(timezone.utc)
        order = self.orders.get_by_id(order_id, for_update=True)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        if order.seller_id != seller_id:
            raise HTTPException(status_code=403, detail="Only the seller can deliver this order")
        if order.status != "paid":
            raise HTTPException(status_code=409, detail="Order is not ready for delivery")
        product = self.products.get_by_id(order.product_id)
        if product and product.fulfillment_type != "manual":
            raise HTTPException(status_code=409, detail="Automatic orders are delivered by the system")
        secret = delivery_info.strip()
        if not secret:
            raise HTTPException(status_code=422, detail="Delivery data is empty")
        order.delivery_secret = encrypt_content(secret)
        order.delivery_info = "Продавец передал данные заказа"
        order.status = "delivered"
        order.delivered_at = now
        order.auto_complete_at = now + timedelta(hours=settings.AUTO_COMPLETE_HOURS)
        order.last_activity_at = now
        self.room.add_event(order.id, "delivered", "Продавец передал товар. Покупателю нужно проверить его перед подтверждением.", actor_id=seller_id, payload={"automatic": False})
        self.notifications.create(
            order.buyer_id,
            "Продавец выдал заказ",
            f"Заказ #{order.id} отмечен как выданный. Проверьте товар, затем подтвердите получение или откройте спор.",
            type="order",
            link=f"/order/{order.id}",
        )
        self.db.commit()
        self.db.refresh(order)
        return order

    def confirm(self, order_id: int, buyer_id: int):
        order = self.orders.get_by_id(order_id, for_update=True)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        if order.buyer_id != buyer_id:
            raise HTTPException(status_code=403, detail="Access denied")
        if order.status != "delivered":
            raise HTTPException(status_code=409, detail="Order has not been delivered")
        self._release_to_seller(order)
        self.room.add_event(order.id, "confirmed", "Покупатель подтвердил получение и завершил сделку.", actor_id=buyer_id)
        self.notifications.create(order.seller_id, "Заказ завершён", f"Покупатель подтвердил заказ #{order.id}. Средства зачислены на баланс.", type="order", link=f"/order/{order.id}")
        self.notifications.create(order.buyer_id, "Заказ завершён", f"Заказ #{order.id} успешно завершён. Можно оставить отзыв.", type="order", link=f"/order/{order.id}")
        self.db.commit()
        self.db.refresh(order)
        return order

    def cancel_pending(self, order_id: int, buyer_id: int):
        order = self.orders.get_by_id(order_id, for_update=True)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        if order.buyer_id != buyer_id:
            raise HTTPException(status_code=403, detail="Access denied")
        if order.status != "pending":
            raise HTTPException(status_code=409, detail="Only unpaid orders can be cancelled")
        now = datetime.now(timezone.utc)
        order.status = "cancelled"
        order.cancelled_at = now
        order.last_activity_at = now
        self.room.add_event(order.id, "cancelled", "Покупатель отменил неоплаченный заказ.", actor_id=buyer_id)
        self.db.commit()
        return {"message": "Order cancelled"}

    def auto_complete(self):
        now = datetime.now(timezone.utc)
        overdue = self.orders.get_overdue(now)
        completed = 0
        for order in overdue:
            self._release_to_seller(order, now=now)
            self.room.add_event(order.id, "auto_completed", "Заказ завершён автоматически по таймеру защиты сделки.")
            self.notifications.create(order.seller_id, "Заказ завершён автоматически", f"Заказ #{order.id} завершён по таймеру.", type="order", link=f"/order/{order.id}")
            self.notifications.create(order.buyer_id, "Заказ завершён автоматически", f"Заказ #{order.id} завершён по таймеру.", type="order", link=f"/order/{order.id}")
            completed += 1
        self.db.commit()
        return {"auto_completed": completed}

    def _release_to_seller(self, order, *, now: datetime | None = None):
        if order.settled_at is not None:
            raise HTTPException(status_code=409, detail="Order is already settled")
        now = now or datetime.now(timezone.utc)
        seller = self.users.get_by_id(order.seller_id, for_update=True)
        if not seller:
            raise HTTPException(status_code=409, detail="Seller not found")
        earnings = Decimal(order.seller_earnings)
        seller.balance = money(Decimal(seller.balance or 0) + earnings)
        seller.withdrawable_balance = money(Decimal(getattr(seller, "withdrawable_balance", 0) or 0) + earnings)
        seller.total_sales = (seller.total_sales or 0) + 1
        order.status = "completed"
        order.completed_at = now
        order.auto_complete_at = None
        order.settled_at = now
        order.last_activity_at = now
        self.balance.add_history(seller.id, earnings, "earning", f"Order #{order.id} completed", "order", order.id)

    def get_by_id(self, order_id: int):
        return self.orders.get_by_id(order_id)

    def buyer_orders(self, buyer_id: int):
        return self.orders.get_by_buyer(buyer_id)

    def seller_orders(self, seller_id: int):
        return self.orders.get_by_seller(seller_id)
