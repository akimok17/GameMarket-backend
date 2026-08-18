from sqlalchemy.orm import Session

from app.models.models import MarketNotification


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, user_id: int, title: str, body: str = "", *, type: str = "info", link: str | None = None):
        item = MarketNotification(user_id=user_id, title=title, body=body, type=type, link=link)
        self.db.add(item)
        self.db.flush()
        return item

    def list(self, user_id: int, limit: int = 50):
        return (
            self.db.query(MarketNotification)
            .filter(MarketNotification.user_id == user_id)
            .order_by(MarketNotification.created_at.desc())
            .limit(limit)
            .all()
        )

    def unread_count(self, user_id: int) -> int:
        return self.db.query(MarketNotification).filter(
            MarketNotification.user_id == user_id,
            MarketNotification.is_read.is_(False),
        ).count()
