import os
from decimal import Decimal
from dotenv import load_dotenv

from app.core.verification_policy import normalize_policy

load_dotenv()


def _as_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv(name: str, default: str = "") -> list[str]:
    return [x.strip().lower() for x in os.getenv(name, default).split(",") if x.strip()]


class Settings:
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./gamemarket.db")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
    COMMISSION_RATE = Decimal(os.getenv("COMMISSION_RATE", "0.05"))
    CONTENT_ENCRYPTION_KEY = os.getenv("CONTENT_ENCRYPTION_KEY", "")
    CORS_ORIGINS = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",") if x.strip()]
    ALLOW_DEV_DEPOSITS = _as_bool("ALLOW_DEV_DEPOSITS", True)
    CREATE_TABLES_ON_STARTUP = _as_bool("CREATE_TABLES_ON_STARTUP", True)
    MIGRATE_LEGACY_SCHEMA = _as_bool("MIGRATE_LEGACY_SCHEMA", True)
    AUTO_COMPLETE_HOURS = int(os.getenv("AUTO_COMPLETE_HOURS", "24"))
    ORDER_WS_TOKEN_MINUTES = int(os.getenv("ORDER_WS_TOKEN_MINUTES", "10"))
    ORDER_ATTACHMENT_MAX_MB = int(os.getenv("ORDER_ATTACHMENT_MAX_MB", "5"))

    # Payments / payouts. Provider credentials always stay on the backend.
    PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "none").strip().lower()  # none | yookassa
    PAYOUT_PROVIDER = os.getenv("PAYOUT_PROVIDER", "manual").strip().lower()  # manual | yookassa | none
    PAYMENT_TIMEOUT_SECONDS = int(os.getenv("PAYMENT_TIMEOUT_SECONDS", "20"))
    DEPOSIT_MIN_RUB = Decimal(os.getenv("DEPOSIT_MIN_RUB", "10"))
    DEPOSIT_MAX_RUB = Decimal(os.getenv("DEPOSIT_MAX_RUB", "150000"))
    WITHDRAWAL_MIN_RUB = Decimal(os.getenv("WITHDRAWAL_MIN_RUB", "100"))
    WITHDRAWAL_MAX_RUB = Decimal(os.getenv("WITHDRAWAL_MAX_RUB", "100000"))

    # YooKassa payments.
    YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "").strip()
    YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")
    YOOKASSA_RETURN_URL = os.getenv("YOOKASSA_RETURN_URL", "").strip()
    # Optional HTTPS return page for Android browser checkout. If empty,
    # PUBLIC_APP_URL/payment-return is used. YooKassa redirect return_url must be
    # an absolute web URL; the return page can then offer a deep link back to the app.
    ANDROID_PAYMENT_RETURN_URL = os.getenv("ANDROID_PAYMENT_RETURN_URL", "").strip()

    # YooKassa payouts use gateway credentials issued when payouts are enabled.
    YOOKASSA_PAYOUT_GATEWAY_ID = os.getenv("YOOKASSA_PAYOUT_GATEWAY_ID", "").strip()
    YOOKASSA_PAYOUT_SECRET_KEY = os.getenv("YOOKASSA_PAYOUT_SECRET_KEY", "")

    # Account verification / OTP.
    VERIFICATION_CODE_TTL_MINUTES = int(os.getenv("VERIFICATION_CODE_TTL_MINUTES", "10"))
    VERIFICATION_RESEND_SECONDS = int(os.getenv("VERIFICATION_RESEND_SECONDS", "60"))
    VERIFICATION_MAX_ATTEMPTS = int(os.getenv("VERIFICATION_MAX_ATTEMPTS", "5"))
    VERIFICATION_MAX_SENDS_PER_HOUR = int(os.getenv("VERIFICATION_MAX_SENDS_PER_HOUR", "5"))
    VERIFICATION_MAX_SENDS_PER_IP_HOUR = int(os.getenv("VERIFICATION_MAX_SENDS_PER_IP_HOUR", "20"))
    OTP_DEV_ECHO = _as_bool("OTP_DEV_ECHO", False)

    # Backward-compatible switches. Policies are more precise and are what the
    # application uses when the corresponding REQUIRE_* flag is enabled.
    REQUIRE_VERIFIED_FOR_SELLING = _as_bool("REQUIRE_VERIFIED_FOR_SELLING", True)
    REQUIRE_VERIFIED_FOR_WITHDRAWAL = _as_bool("REQUIRE_VERIFIED_FOR_WITHDRAWAL", True)
    SELLER_VERIFICATION_POLICY = normalize_policy(os.getenv("SELLER_VERIFICATION_POLICY", "any"))
    WITHDRAWAL_VERIFICATION_POLICY = normalize_policy(os.getenv("WITHDRAWAL_VERIFICATION_POLICY", "both"))
    PASSWORD_RESET_CHANNELS = set(_csv("PASSWORD_RESET_CHANNELS", "email,phone"))

    LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
    LOGIN_LOCK_MINUTES = int(os.getenv("LOGIN_LOCK_MINUTES", "15"))

    # Email delivery.
    SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USERNAME or "").strip()
    SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "GameMarket").strip() or "GameMarket"
    SMTP_REPLY_TO = os.getenv("SMTP_REPLY_TO", "").strip()
    SMTP_SECURITY = os.getenv("SMTP_SECURITY", "starttls").strip().lower()
    SMTP_TIMEOUT_SECONDS = int(os.getenv("SMTP_TIMEOUT_SECONDS", "20"))
    SMTP_TLS_VERSION = os.getenv("SMTP_TLS_VERSION", "auto").strip().lower()

    # SMS provider: smsru | twilio | generic | none
    SMS_PROVIDER = os.getenv("SMS_PROVIDER", "none").strip().lower()
    SMS_TIMEOUT_SECONDS = int(os.getenv("SMS_TIMEOUT_SECONDS", "15"))

    # SMS.RU
    SMSRU_API_ID = os.getenv("SMSRU_API_ID", "").strip()
    SMSRU_FROM = os.getenv("SMSRU_FROM", "").strip()

    # Twilio Programmable Messaging
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM = os.getenv("TWILIO_FROM", "").strip()
    TWILIO_MESSAGING_SERVICE_SID = os.getenv("TWILIO_MESSAGING_SERVICE_SID", "").strip()

    # Custom JSON SMS gateway.
    SMS_PROVIDER_URL = os.getenv("SMS_PROVIDER_URL", "").strip()
    SMS_PROVIDER_TOKEN = os.getenv("SMS_PROVIDER_TOKEN", "")

    SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "support@gamemarket.local")
    PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "http://127.0.0.1:8000").rstrip("/")

    @property
    def payment_provider_configured(self) -> bool:
        if self.PAYMENT_PROVIDER == "yookassa":
            return bool(self.YOOKASSA_SHOP_ID and self.YOOKASSA_SECRET_KEY)
        return False

    @property
    def payout_provider_configured(self) -> bool:
        if self.PAYOUT_PROVIDER == "manual":
            return True
        if self.PAYOUT_PROVIDER == "yookassa":
            return bool(self.YOOKASSA_PAYOUT_GATEWAY_ID and self.YOOKASSA_PAYOUT_SECRET_KEY)
        return False

    @property
    def email_delivery_configured(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_FROM_EMAIL and (not self.SMTP_USERNAME or self.SMTP_PASSWORD))

    @property
    def sms_delivery_configured(self) -> bool:
        if self.SMS_PROVIDER == "smsru":
            return bool(self.SMSRU_API_ID)
        if self.SMS_PROVIDER == "twilio":
            return bool(self.TWILIO_ACCOUNT_SID and self.TWILIO_AUTH_TOKEN and (self.TWILIO_FROM or self.TWILIO_MESSAGING_SERVICE_SID))
        if self.SMS_PROVIDER == "generic":
            return bool(self.SMS_PROVIDER_URL)
        return False

    def validate(self) -> None:
        if not (Decimal("0") <= self.COMMISSION_RATE < Decimal("1")):
            raise RuntimeError("COMMISSION_RATE must be between 0 and 1")
        if self.SMTP_SECURITY not in {"starttls", "ssl", "none"}:
            raise RuntimeError("SMTP_SECURITY must be starttls, ssl or none")
        if self.SMTP_TLS_VERSION not in {"auto", "tls1_2", "tls1_3"}:
            raise RuntimeError("SMTP_TLS_VERSION must be auto, tls1_2 or tls1_3")
        if self.SMS_PROVIDER not in {"none", "smsru", "twilio", "generic"}:
            raise RuntimeError("SMS_PROVIDER must be none, smsru, twilio or generic")
        if self.PAYMENT_PROVIDER not in {"none", "yookassa"}:
            raise RuntimeError("PAYMENT_PROVIDER must be none or yookassa")
        if self.PAYOUT_PROVIDER not in {"none", "manual", "yookassa"}:
            raise RuntimeError("PAYOUT_PROVIDER must be none, manual or yookassa")
        if not (Decimal("0") < self.DEPOSIT_MIN_RUB <= self.DEPOSIT_MAX_RUB):
            raise RuntimeError("Invalid deposit limits")
        if not (Decimal("0") < self.WITHDRAWAL_MIN_RUB <= self.WITHDRAWAL_MAX_RUB):
            raise RuntimeError("Invalid withdrawal limits")
        if not self.PASSWORD_RESET_CHANNELS or not self.PASSWORD_RESET_CHANNELS.issubset({"email", "phone"}):
            raise RuntimeError("PASSWORD_RESET_CHANNELS must contain email and/or phone")

        if self.ENVIRONMENT == "production":
            if self.SECRET_KEY in {"", "dev-secret-change-me", "your-secret-key-change-me"} or len(self.SECRET_KEY) < 32:
                raise RuntimeError("A strong SECRET_KEY is required in production")
            if self.ALLOW_DEV_DEPOSITS:
                raise RuntimeError("ALLOW_DEV_DEPOSITS must be false in production")
            if not self.CONTENT_ENCRYPTION_KEY:
                raise RuntimeError("CONTENT_ENCRYPTION_KEY is required in production")
            if self.OTP_DEV_ECHO:
                raise RuntimeError("OTP_DEV_ECHO must be false in production")
            if "*" in self.CORS_ORIGINS:
                raise RuntimeError("Wildcard CORS is not allowed in production")
            if self.PAYMENT_PROVIDER == "yookassa" and not self.payment_provider_configured:
                raise RuntimeError("YooKassa payments are enabled but shop credentials are missing")
            if self.PAYOUT_PROVIDER == "yookassa" and not self.payout_provider_configured:
                raise RuntimeError("YooKassa payouts are enabled but payout gateway credentials are missing")
            if self.PAYMENT_PROVIDER == "yookassa":
                if not self.PUBLIC_APP_URL.startswith("https://"):
                    raise RuntimeError("PUBLIC_APP_URL must use HTTPS when YooKassa payments are enabled in production")
                for name, value in (("YOOKASSA_RETURN_URL", self.YOOKASSA_RETURN_URL), ("ANDROID_PAYMENT_RETURN_URL", self.ANDROID_PAYMENT_RETURN_URL)):
                    if value and not value.startswith("https://"):
                        raise RuntimeError(f"{name} must be an absolute HTTPS URL in production")

            seller_policy = self.SELLER_VERIFICATION_POLICY if self.REQUIRE_VERIFIED_FOR_SELLING else "none"
            withdrawal_policy = self.WITHDRAWAL_VERIFICATION_POLICY if self.REQUIRE_VERIFIED_FOR_WITHDRAWAL else "none"
            strict_policies = {seller_policy, withdrawal_policy}
            email_required = (
                "email" in strict_policies
                or "both" in strict_policies
                or "email" in self.PASSWORD_RESET_CHANNELS
            )
            phone_required = (
                "phone" in strict_policies
                or "both" in strict_policies
                or "phone" in self.PASSWORD_RESET_CHANNELS
            )
            any_required = "any" in strict_policies
            if email_required and not self.email_delivery_configured:
                raise RuntimeError("Email verification/reset is required but SMTP is not configured")
            if phone_required and not self.sms_delivery_configured:
                raise RuntimeError("Phone verification/reset is required but SMS provider is not configured")
            if any_required and not (self.email_delivery_configured or self.sms_delivery_configured):
                raise RuntimeError("Verification policy 'any' requires at least one delivery provider")


settings = Settings()
settings.validate()
