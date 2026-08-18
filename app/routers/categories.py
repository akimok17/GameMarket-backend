from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_admin
from app.models.models import Category
from app.schemas import CategoryCreate

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("/")
def list_categories(db: Session = Depends(get_db)):
    return db.query(Category).order_by(Category.name.asc()).all()


@router.post("/", status_code=201)
def create_category(data: CategoryCreate, _admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    category = Category(name=data.name.strip(), icon=data.icon.strip() if data.icon else None)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Category already exists")
    db.refresh(category)
    return category
