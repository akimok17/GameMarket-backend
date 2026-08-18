import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.verification_service import VerificationService

if len(sys.argv) != 2:
    raise SystemExit("Usage: python scripts/test_sms_delivery.py +79991234567")

phone = VerificationService._normalize_phone(sys.argv[1])
code = f"{secrets.randbelow(1_000_000):06d}"
provider, message_id = VerificationService(None)._send_sms(phone, code, "verify_account", None)
print("SMS SENT")
print("provider:", provider)
print("message_id:", message_id)
print("test code:", code)
