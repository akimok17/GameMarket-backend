from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories.chat_repository import ChatRepository
from app.repositories.user_repository import UserRepository
from app.schemas import ChatMessageCreate


class ChatService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ChatRepository(db)
        self.users = UserRepository(db)

    def send_message(self, sender_id: int, data: ChatMessageCreate):
        if sender_id == data.receiver_id:
            raise HTTPException(status_code=400, detail="Cannot message yourself")
        if not self.users.get_by_id(data.receiver_id):
            raise HTTPException(status_code=404, detail="Receiver not found")
        message = self.repo.send(sender_id, data.receiver_id, data.message.strip())
        self.db.commit()
        self.db.refresh(message)
        return message

    def get_dialog(self, user_id: int, other_user_id: int, skip: int = 0, limit: int = 100):
        if not self.users.get_by_id(other_user_id):
            raise HTTPException(status_code=404, detail="User not found")
        messages = self.repo.dialog(user_id, other_user_id, skip=skip, limit=limit)
        self.repo.mark_received_read(user_id, other_user_id)
        self.db.commit()
        return messages

    def unread_count(self, user_id: int):
        return {"unread": self.repo.unread_count(user_id)}
