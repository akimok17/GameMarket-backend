from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.schemas import VerificationConfirm, VerificationRequest
from app.services.verification_service import VerificationService

router = APIRouter(prefix="/verification", tags=["verification"])


def _request_ip(request: Request) -> str | None:
    # Behind a trusted reverse proxy, configure it to pass X-Forwarded-For and
    # Uvicorn/your proxy trust settings correctly. Never blindly trust arbitrary
    # X-Forwarded-For from the public internet.
    return request.client.host if request.client else None


@router.get("/public-config")
def public_config():
    return VerificationService.public_config()


@router.get("/status")
def status(current_user=Depends(get_current_user)):
    return VerificationService.verification_status(current_user)


@router.get("/providers")
def providers(current_user=Depends(get_current_user)):
    return {
        "email": {"configured": settings.email_delivery_configured, "provider": "smtp" if settings.email_delivery_configured else None},
        "sms": {"configured": settings.sms_delivery_configured, "provider": settings.SMS_PROVIDER if settings.sms_delivery_configured else None},
        "dev_echo": settings.ENVIRONMENT != "production" and settings.OTP_DEV_ECHO,
    }


@router.post("/request")
def request_code(data: VerificationRequest, request: Request, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return VerificationService(db).issue_for_user(current_user, data.channel, request_ip=_request_ip(request))


@router.post("/confirm")
def confirm_code(data: VerificationConfirm, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return VerificationService(db).confirm_for_user(current_user, data.channel, data.code)
