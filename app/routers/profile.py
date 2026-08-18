from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.schemas import ProfileUpdate, ReviewCreate, ReviewResponse
from app.services.profile_service import ProfileService
from app.services.order_room_service import OrderRoomService

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/me")
def my_profile(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return ProfileService(db).my_profile(current_user.id)


@router.put("/me")
def update_my_profile(data: ProfileUpdate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return ProfileService(db).update(current_user.id, data)


@router.post("/reviews", response_model=ReviewResponse, status_code=201)
def create_review(data: ReviewCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return ProfileService(db).create_review(current_user.id, data)


@router.get("/{user_id}/market-stats")
def market_stats(user_id: int, db: Session = Depends(get_db)):
    ProfileService(db).public_profile(user_id)
    return OrderRoomService(db).seller_stats(user_id)


@router.get("/{user_id}")
def public_profile(user_id: int, db: Session = Depends(get_db)):
    return ProfileService(db).public_profile(user_id)


@router.get("/{user_id}/reviews", response_model=list[ReviewResponse])
def user_reviews(user_id: int, db: Session = Depends(get_db)):
    return ProfileService(db).get_reviews(user_id)
