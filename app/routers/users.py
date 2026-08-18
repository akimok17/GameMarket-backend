from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.schemas import (
    PasswordChange, PasswordResetConfirm, PasswordResetRequest,
    TokenResponse, UserLogin, UserRegister, UserResponse,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


def _request_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/register", response_model=UserResponse, status_code=201)
def register(data: UserRegister, db: Session = Depends(get_db)):
    return UserService(db).register(data)


@router.post("/login", response_model=TokenResponse)
def login(data: UserLogin, db: Session = Depends(get_db)):
    return UserService(db).login(data)


@router.get("/me", response_model=UserResponse)
def me(current_user=Depends(get_current_user)):
    return current_user


@router.put("/me/become-seller")
def become_seller(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return UserService(db).become_seller(current_user.id)


@router.put("/me/password")
def change_password(data: PasswordChange, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return UserService(db).change_password(current_user.id, data.current_password, data.new_password)


@router.post("/password-reset/request")
def password_reset_request(data: PasswordResetRequest, request: Request, db: Session = Depends(get_db)):
    return UserService(db).request_password_reset(
        data.resolved_identifier(),
        channel=data.channel,
        request_ip=_request_ip(request),
    )


@router.post("/password-reset/confirm")
def password_reset_confirm(data: PasswordResetConfirm, db: Session = Depends(get_db)):
    return UserService(db).reset_password(
        data.resolved_identifier(),
        data.code,
        data.new_password,
        channel=data.channel,
    )


@router.post("/me/logout-all")
def logout_all(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return UserService(db).logout_all(current_user.id)
