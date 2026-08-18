from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.models import MarketNotification
from app.schemas import NotificationResponse
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/", response_model=list[NotificationResponse])
def list_notifications(limit: int = Query(30, ge=1, le=100), current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return NotificationService(db).list(current_user.id, limit)


@router.get("/unread-count")
def unread_count(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return {"unread": NotificationService(db).unread_count(current_user.id)}


@router.put("/{notification_id}/read")
def mark_read(notification_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(MarketNotification).filter(
        MarketNotification.id == notification_id,
        MarketNotification.user_id == current_user.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Notification not found")
    item.is_read = True
    db.commit()
    return {"message": "Notification marked as read"}


@router.put("/read-all")
def read_all(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(MarketNotification).filter(
        MarketNotification.user_id == current_user.id,
        MarketNotification.is_read.is_(False),
    ).update({MarketNotification.is_read: True}, synchronize_session=False)
    db.commit()
    return {"message": "All notifications marked as read"}
