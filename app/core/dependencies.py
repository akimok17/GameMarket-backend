from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_token
from app.core.verification_policy import policy_satisfied, policy_text
from app.models.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    try:
        token_version = int(payload.get("ver", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    if token_version != int(user.token_version or 0):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked")
    return user


def get_current_verified_user(current_user: User = Depends(get_current_user)) -> User:
    # Generic verified dependency means at least one confirmed channel.
    if not current_user.is_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verify your email or phone first")
    return current_user


def get_current_seller(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_seller:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Seller access required")
    seller_policy = settings.SELLER_VERIFICATION_POLICY if settings.REQUIRE_VERIFIED_FOR_SELLING else "none"
    if not policy_satisfied(current_user, seller_policy):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=policy_text(seller_policy))
    return current_user


def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
