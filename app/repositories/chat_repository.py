from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from app.models.models import ChatMessage


class ChatRepository:
    def __init__(self, db: Session):
        self.db = db

    def send(self, sender_id: int, receiver_id: int, message: str) -> ChatMessage:
        item = ChatMessage(sender_id=sender_id, receiver_id=receiver_id, message=message)
        self.db.add(item)
        self.db.flush()
        return item

    def dialog(self, user_id: int, other_user_id: int, skip: int = 0, limit: int = 100) -> list[ChatMessage]:
        return self.db.query(ChatMessage).filter(or_(
            and_(ChatMessage.sender_id == user_id, ChatMessage.receiver_id == other_user_id),
            and_(ChatMessage.sender_id == other_user_id, ChatMessage.receiver_id == user_id),
        )).order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc()).offset(skip).limit(limit).all()

    def mark_received_read(self, user_id: int, other_user_id: int) -> int:
        count = self.db.query(ChatMessage).filter(
            ChatMessage.sender_id == other_user_id,
            ChatMessage.receiver_id == user_id,
            ChatMessage.is_read.is_(False),
        ).update({ChatMessage.is_read: True}, synchronize_session=False)
        return count

    def unread_count(self, user_id: int) -> int:
        return self.db.query(ChatMessage).filter(
            ChatMessage.receiver_id == user_id,
            ChatMessage.is_read.is_(False),
        ).count()
