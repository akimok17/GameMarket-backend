from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.models import Order, SupportMessage, SupportTicket, User
from app.schemas import SupportTicketCreate
from app.services.notification_service import NotificationService


class SupportService:
    def __init__(self, db: Session):
        self.db = db
        self.notifications = NotificationService(db)

    def create(self, user_id: int, data: SupportTicketCreate):
        if data.order_id:
            order = self.db.query(Order).filter(Order.id == data.order_id).first()
            if not order:
                raise HTTPException(status_code=404, detail="Order not found")
            if user_id not in {order.buyer_id, order.seller_id}:
                raise HTTPException(status_code=403, detail="You do not have access to this order")
        ticket = SupportTicket(
            user_id=user_id,
            subject=data.subject.strip(),
            category=data.category,
            priority=data.priority,
            order_id=data.order_id,
            status="open",
        )
        self.db.add(ticket)
        self.db.flush()
        self.db.add(SupportMessage(ticket_id=ticket.id, author_id=user_id, message=data.message.strip(), is_staff=False))
        for admin in self.db.query(User).filter(User.is_admin.is_(True), User.is_active.is_(True)).all():
            self.notifications.create(admin.id, "Новое обращение в поддержку", f"Тикет #{ticket.id}: {ticket.subject}", type="support", link=f"/support?ticket={ticket.id}")
        self.db.commit()
        self.db.refresh(ticket)
        return ticket

    def my_tickets(self, user_id: int):
        return self.db.query(SupportTicket).filter(SupportTicket.user_id == user_id).order_by(SupportTicket.updated_at.desc()).all()

    def get_ticket(self, ticket_id: int, requester: User):
        ticket = self.db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if not requester.is_admin and ticket.user_id != requester.id:
            raise HTTPException(status_code=403, detail="Access denied")
        messages = self.db.query(SupportMessage).filter(SupportMessage.ticket_id == ticket.id).order_by(SupportMessage.created_at.asc()).all()
        return ticket, messages

    def reply(self, ticket_id: int, requester: User, message: str):
        ticket, _ = self.get_ticket(ticket_id, requester)
        if ticket.status == "closed":
            raise HTTPException(status_code=409, detail="Ticket is closed")
        is_staff = bool(requester.is_admin)
        item = SupportMessage(ticket_id=ticket.id, author_id=requester.id, message=message.strip(), is_staff=is_staff)
        self.db.add(item)
        ticket.updated_at = datetime.now(timezone.utc)
        ticket.status = "awaiting_user" if is_staff else "awaiting_support"
        if is_staff:
            self.notifications.create(
                ticket.user_id,
                "Ответ поддержки",
                f"Поддержка ответила в обращении #{ticket.id}: {ticket.subject}",
                type="support",
                link=f"/support?ticket={ticket.id}",
            )
        self.db.commit()
        self.db.refresh(item)
        return item

    def close(self, ticket_id: int, requester: User):
        ticket, _ = self.get_ticket(ticket_id, requester)
        ticket.status = "closed"
        ticket.closed_at = datetime.now(timezone.utc)
        ticket.updated_at = ticket.closed_at
        self.db.commit()
        return ticket

    def admin_list(self, status: str | None = None, limit: int = 100):
        query = self.db.query(SupportTicket)
        if status:
            query = query.filter(SupportTicket.status == status)
        return query.order_by(SupportTicket.updated_at.desc()).limit(limit).all()

    def admin_set_status(self, ticket_id: int, status: str):
        ticket = self.db.query(SupportTicket).filter(SupportTicket.id == ticket_id).with_for_update().first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        ticket.status = status
        ticket.updated_at = datetime.now(timezone.utc)
        if status == "closed":
            ticket.closed_at = ticket.updated_at
        elif ticket.closed_at:
            ticket.closed_at = None
        self.db.commit()
        return ticket
