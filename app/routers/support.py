from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_admin, get_current_user
from app.schemas import SupportReplyCreate, SupportStatusUpdate, SupportTicketCreate, SupportTicketResponse
from app.services.support_service import SupportService

router = APIRouter(prefix="/support", tags=["support"])


@router.post("/tickets", response_model=SupportTicketResponse, status_code=201)
def create_ticket(data: SupportTicketCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return SupportService(db).create(current_user.id, data)


@router.get("/tickets", response_model=list[SupportTicketResponse])
def my_tickets(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return SupportService(db).my_tickets(current_user.id)


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    ticket, messages = SupportService(db).get_ticket(ticket_id, current_user)
    return {"ticket": ticket, "messages": messages}


@router.post("/tickets/{ticket_id}/reply")
def reply(ticket_id: int, data: SupportReplyCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return SupportService(db).reply(ticket_id, current_user, data.message)


@router.post("/tickets/{ticket_id}/close", response_model=SupportTicketResponse)
def close_ticket(ticket_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return SupportService(db).close(ticket_id, current_user)


@router.get("/admin/tickets", response_model=list[SupportTicketResponse])
def admin_tickets(status: str | None = None, limit: int = Query(100, ge=1, le=500), _admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    return SupportService(db).admin_list(status, limit)


@router.post("/admin/tickets/{ticket_id}/reply")
def admin_reply(ticket_id: int, data: SupportReplyCreate, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    return SupportService(db).reply(ticket_id, admin, data.message)


@router.put("/admin/tickets/{ticket_id}/status", response_model=SupportTicketResponse)
def admin_status(ticket_id: int, data: SupportStatusUpdate, _admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    return SupportService(db).admin_set_status(ticket_id, data.status)
