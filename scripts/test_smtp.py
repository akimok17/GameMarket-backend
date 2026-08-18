import smtplib
import ssl
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.services.verification_service import VerificationService

print(f"Host: {settings.SMTP_HOST}:{settings.SMTP_PORT}")
print(f"Security: {settings.SMTP_SECURITY}")
print(f"TLS version: {settings.SMTP_TLS_VERSION}")
print(f"Username: {settings.SMTP_USERNAME}")

ctx = VerificationService._smtp_ssl_context()
if settings.SMTP_SECURITY == "ssl":
    smtp = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT_SECONDS, context=ctx)
else:
    smtp = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT_SECONDS)

with smtp:
    code, msg = smtp.ehlo()
    print("EHLO:", code, msg.decode(errors="replace") if isinstance(msg, bytes) else msg)
    if settings.SMTP_SECURITY == "starttls":
        print("STARTTLS:", smtp.starttls(context=ctx)[0])
        smtp.ehlo()
    if settings.SMTP_USERNAME:
        smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        print("AUTH OK")
    print("NOOP:", smtp.noop())
print("SMTP CONFIG OK")
