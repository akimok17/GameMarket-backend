from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import smtplib
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import make_msgid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.verification_policy import missing_channels, policy_satisfied, policy_text
from app.models.models import User, VerificationCode


class VerificationService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _hash_code(code: str) -> str:
        return hmac.new(settings.SECRET_KEY.encode("utf-8"), code.encode("utf-8"), hashlib.sha256).hexdigest()

    @staticmethod
    def _generate_code() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    @staticmethod
    def _normalize_phone(value: str) -> str:
        raw = re.sub(r"[^0-9+]", "", str(value or "").strip())
        if raw.startswith("00"):
            raw = "+" + raw[2:]
        digits = re.sub(r"\D", "", raw)
        # Common RU convenience: 8XXXXXXXXXX -> +7XXXXXXXXXX
        if raw.startswith("8") and len(digits) == 11:
            digits = "7" + digits[1:]
        if not (8 <= len(digits) <= 15):
            raise HTTPException(status_code=400, detail="Phone must be in international format, e.g. +79991234567")
        return "+" + digits

    @staticmethod
    def _normalize_email(value: str) -> str:
        value = str(value or "").strip().lower()
        if not value or "@" not in value:
            raise HTTPException(status_code=400, detail="Invalid email")
        return value

    def _destination(self, user: User, channel: str) -> str:
        if channel == "email":
            if not user.email:
                raise HTTPException(status_code=400, detail="Email is not configured")
            return self._normalize_email(user.email)
        if channel == "phone":
            if not user.phone:
                raise HTTPException(status_code=400, detail="Phone is not configured")
            return self._normalize_phone(user.phone)
        raise HTTPException(status_code=400, detail="Unsupported verification channel")

    def _ensure_channel_available(self, channel: str) -> None:
        if channel == "email":
            if not settings.email_delivery_configured and not (
                settings.ENVIRONMENT != "production" and settings.OTP_DEV_ECHO
            ):
                raise HTTPException(status_code=503, detail="Email delivery is temporarily unavailable")
            return
        if channel == "phone":
            if not settings.sms_delivery_configured and not (
                settings.ENVIRONMENT != "production" and settings.OTP_DEV_ECHO
            ):
                raise HTTPException(status_code=503, detail="SMS delivery is temporarily unavailable")
            return
        raise HTTPException(status_code=400, detail="Unsupported verification channel")

    def _check_send_limits(self, user_id: int, channel: str, purpose: str, request_ip: str | None = None) -> None:
        latest = (
            self.db.query(VerificationCode)
            .filter(
                VerificationCode.user_id == user_id,
                VerificationCode.channel == channel,
                VerificationCode.purpose == purpose,
            )
            .order_by(VerificationCode.created_at.desc())
            .first()
        )
        now = datetime.now(timezone.utc)
        if latest and latest.created_at:
            created = latest.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            elapsed = (now - created).total_seconds()
            if elapsed < settings.VERIFICATION_RESEND_SECONDS:
                wait = max(1, settings.VERIFICATION_RESEND_SECONDS - int(elapsed))
                raise HTTPException(status_code=429, detail=f"Wait {wait} seconds before requesting another code")

        hour_ago = now - timedelta(hours=1)
        sent_last_hour = (
            self.db.query(VerificationCode)
            .filter(
                VerificationCode.user_id == user_id,
                VerificationCode.channel == channel,
                VerificationCode.purpose == purpose,
                VerificationCode.created_at >= hour_ago,
            )
            .count()
        )
        if sent_last_hour >= settings.VERIFICATION_MAX_SENDS_PER_HOUR:
            raise HTTPException(status_code=429, detail="Too many verification codes requested. Try again later")

        if request_ip:
            ip_count = (
                self.db.query(VerificationCode)
                .filter(
                    VerificationCode.request_ip == request_ip,
                    VerificationCode.created_at >= hour_ago,
                )
                .count()
            )
            if ip_count >= settings.VERIFICATION_MAX_SENDS_PER_IP_HOUR:
                raise HTTPException(status_code=429, detail="Too many verification requests from this network. Try again later")

    @staticmethod
    def _email_content(code: str, purpose: str) -> tuple[str, str, str]:
        if purpose == "password_reset":
            title = "Восстановление пароля"
            subject = "Код восстановления GameMarket"
            intro = "Вы запросили восстановление пароля GameMarket."
        else:
            title = "Подтверждение аккаунта"
            subject = "Код подтверждения GameMarket"
            intro = "Подтвердите email для защиты аккаунта GameMarket."

        plain = (
            f"{intro}\n\nКод: {code}\n\n"
            f"Код действует {settings.VERIFICATION_CODE_TTL_MINUTES} минут. "
            "Никому не сообщайте этот код. Если вы не запрашивали его, проигнорируйте сообщение."
        )
        html = f"""<!doctype html>
<html><body style="margin:0;background:#0b0d1a;color:#eef0ff;font-family:Arial,sans-serif">
<div style="max-width:560px;margin:32px auto;padding:0 16px">
  <div style="background:#141831;border:1px solid #2b3158;border-radius:20px;padding:30px">
    <div style="font-size:24px;font-weight:800;margin-bottom:20px">Game<span style="color:#7c5cff">Market</span></div>
    <h1 style="font-size:22px;margin:0 0 12px">{title}</h1>
    <p style="color:#aeb5d4;line-height:1.55">{intro}</p>
    <div style="font-size:34px;letter-spacing:8px;font-weight:800;text-align:center;background:#0e1124;border-radius:14px;padding:18px;margin:24px 0;color:#8d73ff">{code}</div>
    <p style="color:#aeb5d4;font-size:14px;line-height:1.55">Код действует {settings.VERIFICATION_CODE_TTL_MINUTES} минут. Никому не сообщайте его.</p>
    <p style="color:#6f789f;font-size:12px;margin-top:24px">Если вы не запрашивали этот код, просто проигнорируйте письмо.</p>
  </div>
</div></body></html>"""
        return subject, plain, html

    @staticmethod
    def _smtp_ssl_context() -> ssl.SSLContext:
        context = ssl.create_default_context()
        tls_version = settings.SMTP_TLS_VERSION
        if tls_version == "tls1_2":
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.maximum_version = ssl.TLSVersion.TLSv1_2
        elif tls_version == "tls1_3":
            context.minimum_version = ssl.TLSVersion.TLSv1_3
            context.maximum_version = ssl.TLSVersion.TLSv1_3
        return context

    def _send_email(self, destination: str, code: str, purpose: str) -> tuple[str, str | None]:
        if not settings.email_delivery_configured:
            if settings.ENVIRONMENT != "production" and settings.OTP_DEV_ECHO:
                return "dev", None
            raise HTTPException(status_code=503, detail="Email delivery is not configured")

        subject, plain, html = self._email_content(code, purpose)
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
        msg["To"] = destination
        msg["Message-ID"] = make_msgid(domain=settings.SMTP_FROM_EMAIL.split("@")[-1] if "@" in settings.SMTP_FROM_EMAIL else None)
        if settings.SMTP_REPLY_TO:
            msg["Reply-To"] = settings.SMTP_REPLY_TO
        msg.set_content(plain)
        msg.add_alternative(html, subtype="html")

        context = self._smtp_ssl_context()
        try:
            if settings.SMTP_SECURITY == "ssl":
                smtp = smtplib.SMTP_SSL(
                    settings.SMTP_HOST,
                    settings.SMTP_PORT,
                    timeout=settings.SMTP_TIMEOUT_SECONDS,
                    context=context,
                )
            else:
                smtp = smtplib.SMTP(
                    settings.SMTP_HOST,
                    settings.SMTP_PORT,
                    timeout=settings.SMTP_TIMEOUT_SECONDS,
                )
            with smtp:
                smtp.ehlo()
                if settings.SMTP_SECURITY == "starttls":
                    smtp.starttls(context=context)
                    smtp.ehlo()
                if settings.SMTP_USERNAME:
                    smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                refused = smtp.send_message(msg)
                if refused:
                    raise RuntimeError("recipient refused")
        except (smtplib.SMTPException, OSError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=f"Email delivery failed: {type(exc).__name__}") from exc
        return "smtp", msg.get("Message-ID")

    @staticmethod
    def _sms_text(code: str, purpose: str) -> str:
        action = "восстановления пароля" if purpose == "password_reset" else "подтверждения аккаунта"
        return (
            f"GameMarket: код {action} {code}. "
            f"Действует {settings.VERIFICATION_CODE_TTL_MINUTES} мин. Никому не сообщайте код."
        )

    def _send_sms_smsru(self, destination: str, code: str, purpose: str, request_ip: str | None) -> tuple[str, str | None]:
        phone = re.sub(r"\D", "", destination)
        data = {
            "api_id": settings.SMSRU_API_ID,
            "to": phone,
            "msg": self._sms_text(code, purpose),
            "json": "1",
        }
        if settings.SMSRU_FROM:
            data["from"] = settings.SMSRU_FROM
        if request_ip:
            data["ip"] = request_ip
        request = urllib.request.Request(
            "https://sms.ru/sms/send",
            data=urllib.parse.urlencode(data).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=settings.SMS_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("status") != "OK":
                raise RuntimeError(payload.get("status_text") or f"SMS.RU code {payload.get('status_code')}")
            row = (payload.get("sms") or {}).get(phone) or {}
            if row.get("status") != "OK":
                raise RuntimeError(row.get("status_text") or f"SMS.RU code {row.get('status_code')}")
            return "smsru", row.get("sms_id")
        except (urllib.error.URLError, ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=f"SMS delivery failed: {str(exc)[:160]}") from exc

    def _send_sms_twilio(self, destination: str, code: str, purpose: str) -> tuple[str, str | None]:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"
        data = {"To": destination, "Body": self._sms_text(code, purpose)}
        if settings.TWILIO_MESSAGING_SERVICE_SID:
            data["MessagingServiceSid"] = settings.TWILIO_MESSAGING_SERVICE_SID
        else:
            data["From"] = settings.TWILIO_FROM
        basic = base64.b64encode(
            f"{settings.TWILIO_ACCOUNT_SID}:{settings.TWILIO_AUTH_TOKEN}".encode("utf-8")
        ).decode("ascii")
        request = urllib.request.Request(
            url,
            data=urllib.parse.urlencode(data).encode("utf-8"),
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=settings.SMS_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
            sid = payload.get("sid")
            if not sid:
                raise RuntimeError(payload.get("message") or "Twilio did not return message SID")
            return "twilio", sid
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read().decode("utf-8"))
                message = body.get("message") or f"HTTP {exc.code}"
            except Exception:
                message = f"HTTP {exc.code}"
            raise HTTPException(status_code=503, detail=f"SMS delivery failed: {message[:160]}") from exc
        except (urllib.error.URLError, ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=f"SMS delivery failed: {str(exc)[:160]}") from exc

    def _send_sms_generic(self, destination: str, code: str, purpose: str, request_ip: str | None) -> tuple[str, str | None]:
        payload = json.dumps({
            "phone": destination,
            "message": self._sms_text(code, purpose),
            "purpose": purpose,
            "ip": request_ip,
        }).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if settings.SMS_PROVIDER_TOKEN:
            headers["Authorization"] = f"Bearer {settings.SMS_PROVIDER_TOKEN}"
        request = urllib.request.Request(settings.SMS_PROVIDER_URL, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=settings.SMS_TIMEOUT_SECONDS) as response:
                raw = response.read()
                if response.status >= 300:
                    raise RuntimeError(f"HTTP {response.status}")
            message_id = None
            if raw:
                try:
                    parsed = json.loads(raw.decode("utf-8"))
                    message_id = str(parsed.get("id") or parsed.get("message_id") or parsed.get("sid") or "") or None
                except Exception:
                    pass
            return "generic", message_id
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"SMS delivery failed: {type(exc).__name__}") from exc

    def _send_sms(self, destination: str, code: str, purpose: str, request_ip: str | None = None) -> tuple[str, str | None]:
        if not settings.sms_delivery_configured:
            if settings.ENVIRONMENT != "production" and settings.OTP_DEV_ECHO:
                return "dev", None
            raise HTTPException(status_code=503, detail="SMS delivery is not configured")
        if settings.SMS_PROVIDER == "smsru":
            return self._send_sms_smsru(destination, code, purpose, request_ip)
        if settings.SMS_PROVIDER == "twilio":
            return self._send_sms_twilio(destination, code, purpose)
        if settings.SMS_PROVIDER == "generic":
            return self._send_sms_generic(destination, code, purpose, request_ip)
        raise HTTPException(status_code=503, detail="SMS delivery is not configured")

    def issue_for_user(
        self,
        user: User,
        channel: str,
        purpose: str = "verify_account",
        request_ip: str | None = None,
    ):
        self._ensure_channel_available(channel)
        destination = self._destination(user, channel)
        if purpose == "verify_account":
            if channel == "email" and user.email_verified_at:
                return {"message": "Email is already verified", "verified": True, "channel": "email"}
            if channel == "phone" and user.phone_verified_at:
                return {"message": "Phone is already verified", "verified": True, "channel": "phone"}

        self._check_send_limits(user.id, channel, purpose, request_ip)
        code = self._generate_code()
        now = datetime.now(timezone.utc)
        item = VerificationCode(
            user_id=user.id,
            channel=channel,
            purpose=purpose,
            destination=destination,
            code_hash=self._hash_code(code),
            expires_at=now + timedelta(minutes=settings.VERIFICATION_CODE_TTL_MINUTES),
            request_ip=request_ip,
        )
        self.db.add(item)
        self.db.flush()

        try:
            if channel == "email":
                provider, provider_message_id = self._send_email(destination, code, purpose)
            else:
                provider, provider_message_id = self._send_sms(destination, code, purpose, request_ip)
        except Exception:
            self.db.rollback()
            raise

        self.db.query(VerificationCode).filter(
            VerificationCode.user_id == user.id,
            VerificationCode.channel == channel,
            VerificationCode.purpose == purpose,
            VerificationCode.id != item.id,
            VerificationCode.consumed_at.is_(None),
        ).update({VerificationCode.consumed_at: now}, synchronize_session=False)

        item.provider = provider
        item.provider_message_id = provider_message_id
        item.sent_at = now
        self.db.commit()

        result = {
            "message": "Verification code sent",
            "channel": channel,
            "destination": self._mask(destination, channel),
            "provider": provider,
            "expires_in_seconds": settings.VERIFICATION_CODE_TTL_MINUTES * 60,
            "resend_after_seconds": settings.VERIFICATION_RESEND_SECONDS,
        }
        if provider == "dev" and settings.ENVIRONMENT != "production" and settings.OTP_DEV_ECHO:
            result["dev_code"] = code
        return result

    def confirm_for_user(self, user: User, channel: str, code: str, purpose: str = "verify_account"):
        now = datetime.now(timezone.utc)
        item = (
            self.db.query(VerificationCode)
            .filter(
                VerificationCode.user_id == user.id,
                VerificationCode.channel == channel,
                VerificationCode.purpose == purpose,
                VerificationCode.consumed_at.is_(None),
            )
            .order_by(VerificationCode.created_at.desc())
            .with_for_update()
            .first()
        )
        if not item:
            raise HTTPException(status_code=400, detail="Request a new verification code")
        expires = item.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= now:
            raise HTTPException(status_code=400, detail="Verification code expired")
        if item.attempts >= settings.VERIFICATION_MAX_ATTEMPTS:
            raise HTTPException(status_code=429, detail="Too many attempts. Request a new code")

        item.attempts += 1
        if not hmac.compare_digest(item.code_hash, self._hash_code(code)):
            self.db.commit()
            raise HTTPException(status_code=400, detail="Invalid verification code")

        current_destination = self._destination(user, channel)
        if current_destination != item.destination:
            self.db.rollback()
            raise HTTPException(status_code=409, detail="Email or phone changed. Request a new code")

        item.consumed_at = now
        if purpose == "verify_account":
            if channel == "email":
                user.email_verified_at = now
            else:
                user.phone_verified_at = now
        self.db.commit()
        return {"message": f"{channel.title()} verified", "verified": True, "channel": channel}

    def _infer_reset_channel(self, identifier: str, channel: str | None) -> tuple[str, str]:
        identifier = str(identifier or "").strip()
        if channel:
            channel = channel.strip().lower()
        if not channel:
            channel = "email" if "@" in identifier else "phone"
        if channel not in {"email", "phone"}:
            raise HTTPException(status_code=400, detail="Password reset channel must be email or phone")
        if channel not in settings.PASSWORD_RESET_CHANNELS:
            raise HTTPException(status_code=503, detail=f"Password reset by {channel} is disabled")
        self._ensure_channel_available(channel)
        normalized = self._normalize_email(identifier) if channel == "email" else self._normalize_phone(identifier)
        return channel, normalized

    def _find_user_for_reset(self, identifier: str, channel: str) -> User | None:
        if channel == "email":
            return self.db.query(User).filter(User.email.ilike(identifier)).first()
        digits = re.sub(r"\D", "", identifier)
        variants = {identifier, digits, "+" + digits}
        if digits.startswith("7") and len(digits) == 11:
            variants.add("8" + digits[1:])
        return self.db.query(User).filter(User.phone.in_(list(variants))).first()

    def request_password_reset(self, identifier: str, channel: str | None = None, request_ip: str | None = None):
        # Provider availability is checked before lookup so the response doesn't
        # reveal whether an account exists when a delivery channel is offline.
        try:
            channel, normalized = self._infer_reset_channel(identifier, channel)
        except HTTPException as exc:
            if exc.status_code == 503:
                raise
            # Keep account enumeration resistance for malformed / unknown input.
            time.sleep(0.12)
            return {"message": "If the account exists, a reset code has been sent", "channel": channel or "unknown"}

        generic = {
            "message": "If the account exists, a reset code has been sent",
            "channel": channel,
            "resend_after_seconds": settings.VERIFICATION_RESEND_SECONDS,
        }
        user = self._find_user_for_reset(normalized, channel)
        if not user or not user.is_active:
            time.sleep(0.12)
            return generic

        result = self.issue_for_user(user, channel, purpose="password_reset", request_ip=request_ip)
        if result.get("dev_code"):
            generic["dev_code"] = result["dev_code"]
        return generic

    def confirm_password_reset(self, identifier: str, channel: str | None, code: str):
        channel, normalized = self._infer_reset_channel(identifier, channel)
        user = self._find_user_for_reset(normalized, channel)
        if not user or not user.is_active:
            raise HTTPException(status_code=400, detail="Invalid reset request")
        self.confirm_for_user(user, channel, code, purpose="password_reset")
        return user

    def consume_reset_codes(self, user_id: int) -> None:
        now = datetime.now(timezone.utc)
        self.db.query(VerificationCode).filter(
            VerificationCode.user_id == user_id,
            VerificationCode.purpose == "password_reset",
            VerificationCode.consumed_at.is_(None),
        ).update({VerificationCode.consumed_at: now}, synchronize_session=False)

    @staticmethod
    def verification_status(user: User) -> dict:
        seller_policy = settings.SELLER_VERIFICATION_POLICY if settings.REQUIRE_VERIFIED_FOR_SELLING else "none"
        withdrawal_policy = settings.WITHDRAWAL_VERIFICATION_POLICY if settings.REQUIRE_VERIFIED_FOR_WITHDRAWAL else "none"
        return {
            "is_verified": user.is_verified,
            "email_verified": bool(user.email_verified_at),
            "phone_verified": bool(user.phone_verified_at),
            "email": user.email,
            "phone": user.phone,
            "email_delivery_configured": settings.email_delivery_configured,
            "sms_delivery_configured": settings.sms_delivery_configured,
            "sms_provider": settings.SMS_PROVIDER if settings.sms_delivery_configured else None,
            "seller_policy": seller_policy,
            "withdrawal_policy": withdrawal_policy,
            "seller_ready": policy_satisfied(user, seller_policy),
            "withdrawal_ready": policy_satisfied(user, withdrawal_policy),
            "seller_missing": missing_channels(user, seller_policy),
            "withdrawal_missing": missing_channels(user, withdrawal_policy),
            "seller_requirement": policy_text(seller_policy),
            "withdrawal_requirement": policy_text(withdrawal_policy),
        }

    @staticmethod
    def public_config() -> dict:
        seller_policy = settings.SELLER_VERIFICATION_POLICY if settings.REQUIRE_VERIFIED_FOR_SELLING else "none"
        withdrawal_policy = settings.WITHDRAWAL_VERIFICATION_POLICY if settings.REQUIRE_VERIFIED_FOR_WITHDRAWAL else "none"
        return {
            "email_delivery_configured": settings.email_delivery_configured,
            "sms_delivery_configured": settings.sms_delivery_configured,
            "password_reset_channels": sorted(settings.PASSWORD_RESET_CHANNELS),
            "seller_policy": seller_policy,
            "withdrawal_policy": withdrawal_policy,
            "seller_requirement": policy_text(seller_policy),
            "withdrawal_requirement": policy_text(withdrawal_policy),
            "otp_ttl_minutes": settings.VERIFICATION_CODE_TTL_MINUTES,
        }

    @staticmethod
    def _mask(value: str, channel: str) -> str:
        if channel == "email" and "@" in value:
            name, domain = value.split("@", 1)
            return (name[:2] + "***@" + domain) if len(name) > 2 else ("***@" + domain)
        digits = re.sub(r"\D", "", value)
        if len(digits) <= 4:
            return "***"
        return "+" + "*" * max(0, len(digits) - 4) + digits[-4:]
