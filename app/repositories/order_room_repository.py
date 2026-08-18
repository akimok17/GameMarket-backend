from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.models import Order, OrderEvent, OrderMessage


class OrderRoomRepository:
    def __init__(self, db: Session):
        self.db = db

    def add_event(self, order_id: int, event_type: str, text: str, *, actor_id: int | None = None, payload: dict | None = None) -> OrderEvent:
        event = OrderEvent(
            order_id=order_id,
            actor_id=actor_id,
            event_type=event_type,
            text=text,
            payload=payload or {},
        )
        self.db.add(event)
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if order:
            order.last_activity_at = datetime.now(timezone.utc)
        self.db.flush()
        return event

    def events(self, order_id: int, limit: int = 250) -> list[OrderEvent]:
        return (
            self.db.query(OrderEvent)
            .filter(OrderEvent.order_id == order_id)
            .order_by(OrderEvent.created_at.asc(), OrderEvent.id.asc())
            .limit(limit)
            .all()
        )

    def add_message(
        self,
        order_id: int,
        sender_id: int,
        *,
        message: str | None = None,
        attachment_url: str | None = None,
        attachment_name: str | None = None,
        attachment_mime: str | None = None,
    ) -> OrderMessage:
        row = OrderMessage(
            order_id=order_id,
            sender_id=sender_id,
            message=message,
            attachment_url=attachment_url,
            attachment_name=attachment_name,
            attachment_mime=attachment_mime,
        )
        self.db.add(row)
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if order:
            order.last_activity_at = datetime.now(timezone.utc)
        self.db.flush()
        return row

    def messages(self, order_id: int, *, limit: int = 200, before_id: int | None = None) -> list[OrderMessage]:
        q = self.db.query(OrderMessage).filter(OrderMessage.order_id == order_id)
        if before_id:
            q = q.filter(OrderMessage.id < before_id)
        rows = q.order_by(OrderMessage.id.desc()).limit(limit).all()
        return list(reversed(rows))

    def mark_read(self, order_id: int, reader_id: int) -> list[int]:
        now = datetime.now(timezone.utc)
        rows = (
            self.db.query(OrderMessage)
            .filter(
                OrderMessage.order_id == order_id,
                OrderMessage.sender_id != reader_id,
                OrderMessage.is_read.is_(False),
            )
            .all()
        )
        ids = []
        for row in rows:
            row.is_read = True
            row.read_at = now
            ids.append(row.id)
        if ids:
            self.db.flush()
        return ids

    def first_seller_message_after(self, order_id: int, seller_id: int, after: datetime):
        return (
            self.db.query(OrderMessage)
            .filter(
                OrderMessage.order_id == order_id,
                OrderMessage.sender_id == seller_id,
                OrderMessage.created_at >= after,
            )
            .order_by(OrderMessage.created_at.asc())
            .first()
        )
