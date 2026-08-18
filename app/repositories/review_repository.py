from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.models import Review


class ReviewRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_order_and_reviewer(self, order_id: int, reviewer_id: int) -> Review | None:
        return self.db.query(Review).filter(Review.order_id == order_id, Review.reviewer_id == reviewer_id).first()

    def create(self, **data) -> Review:
        review = Review(**data)
        self.db.add(review)
        self.db.flush()
        return review

    def get_by_target_user(self, target_user_id: int) -> list[Review]:
        return self.db.query(Review).filter(Review.target_user_id == target_user_id).order_by(Review.created_at.desc()).all()

    def average_for_user(self, target_user_id: int):
        return self.db.query(func.avg(Review.rating)).filter(Review.target_user_id == target_user_id).scalar()
