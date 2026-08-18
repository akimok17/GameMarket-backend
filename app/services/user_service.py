from datetime import datetime, timedelta, timezone
import re

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.core.verification_policy import policy_satisfied, policy_text
from app.repositories.user_repository import UserRepository
from app.schemas import TokenResponse, UserLogin, UserRegister
from app.services.verification_service import VerificationService


def normalize_phone(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if value.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if len(digits) < 8 or len(digits) > 15:
        raise HTTPException(status_code=422, detail="Invalid phone number")
    return "+" + digits



class UserService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = UserRepository(db)

    def register(self, data: UserRegister):
        username = data.username.strip()
        email = str(data.email).strip().lower()
        phone = normalize_phone(data.phone)
        if self.repo.get_by_username(username):
            raise HTTPException(status_code=409, detail="Username already taken")
        if self.repo.get_by_email(email):
            raise HTTPException(status_code=409, detail="Email already registered")
        if phone and self.repo.get_by_phone(phone):
            raise HTTPException(status_code=409, detail="Phone already registered")
        try:
            user = self.repo.create(
                username=username,
                email=email,
                password_hash=hash_password(data.password),
                full_name=data.full_name.strip() if data.full_name else None,
                phone=phone,
            )
            self.db.commit()
            self.db.refresh(user)
            return user
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(status_code=409, detail="Username or email already exists")

    def login(self, data: UserLogin) -> TokenResponse:
        login = data.username.strip()
        user = self.repo.get_by_email(login) if "@" in login else self.repo.get_by_username(login)
        now = datetime.now(timezone.utc)
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if user.locked_until:
            locked_until = user.locked_until if user.locked_until.tzinfo else user.locked_until.replace(tzinfo=timezone.utc)
            if locked_until > now:
                raise HTTPException(status_code=429, detail="Too many failed login attempts. Try again later")
            user.locked_until = None
            user.failed_login_attempts = 0
        if not verify_password(data.password, user.password_hash):
            user.failed_login_attempts = int(user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= settings.LOGIN_MAX_ATTEMPTS:
                user.locked_until = now + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
                user.failed_login_attempts = 0
            self.db.commit()
            raise HTTPException(status_code=401, detail="Invalid credentials")
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        user.last_active = now
        self.db.commit()
        self.db.refresh(user)
        return TokenResponse(access_token=create_access_token(user.id, {"ver": int(user.token_version or 0)}), user=user)

    def become_seller(self, user_id: int):
        user = self.repo.get_by_id(user_id, for_update=True)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        seller_policy = settings.SELLER_VERIFICATION_POLICY if settings.REQUIRE_VERIFIED_FOR_SELLING else "none"
        if not policy_satisfied(user, seller_policy):
            raise HTTPException(status_code=403, detail=policy_text(seller_policy))
        user.is_seller = True
        self.db.commit()
        return {"message": "Seller mode enabled"}

    def change_password(self, user_id: int, current_password: str, new_password: str):
        user = self.repo.get_by_id(user_id, for_update=True)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if not verify_password(current_password, user.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        if verify_password(new_password, user.password_hash):
            raise HTTPException(status_code=400, detail="New password must be different")
        user.password_hash = hash_password(new_password)
        user.token_version = int(user.token_version or 0) + 1
        self.db.commit()
        return {"message": "Password changed"}

    def request_password_reset(self, identifier: str, channel: str | None = None, request_ip: str | None = None):
        return VerificationService(self.db).request_password_reset(identifier, channel=channel, request_ip=request_ip)

    def reset_password(self, identifier: str, code: str, new_password: str, channel: str | None = None):
        verification = VerificationService(self.db)
        user = verification.confirm_password_reset(identifier, channel, code)
        if verify_password(new_password, user.password_hash):
            raise HTTPException(status_code=400, detail="New password must be different")
        user.password_hash = hash_password(new_password)
        user.token_version = int(user.token_version or 0) + 1
        verification.consume_reset_codes(user.id)
        self.db.commit()
        return {"message": "Password reset successful"}

    def logout_all(self, user_id: int):
        user = self.repo.get_by_id(user_id, for_update=True)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.token_version = int(user.token_version or 0) + 1
        self.db.commit()
        return {"message": "All sessions revoked"}
