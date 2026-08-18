from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.schemas import ProductResponse
from app.services.favorite_service import FavoriteService

router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.get("/", response_model=list[ProductResponse])
def list_favorites(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return FavoriteService(db).get_all(current_user.id)


@router.post("/{product_id}")
def add_favorite(product_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return FavoriteService(db).add(current_user.id, product_id)


@router.delete("/{product_id}")
def remove_favorite(product_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return FavoriteService(db).remove(current_user.id, product_id)
