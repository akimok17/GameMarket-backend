from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.schemas import ChatMessageCreate, ChatMessageResponse
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/unread")
def unread(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return ChatService(db).unread_count(current_user.id)


@router.post("/send", response_model=ChatMessageResponse, status_code=201)
def send_message(data: ChatMessageCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return ChatService(db).send_message(current_user.id, data)


@router.get("/dialog/{other_user_id}", response_model=list[ChatMessageResponse])
def dialog(
    other_user_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ChatService(db).get_dialog(current_user.id, other_user_id, skip, limit)
