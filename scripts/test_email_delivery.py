import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.verification_service import VerificationService

if len(sys.argv) != 2 or "@" not in sys.argv[1]:
    raise SystemExit("Usage: python scripts/test_email_delivery.py recipient@example.com")

recipient = sys.argv[1].strip()
code = f"{secrets.randbelow(1_000_000):06d}"
provider, message_id = VerificationService(None)._send_email(recipient, code, "verify_account")
print("EMAIL SENT")
print("provider:", provider)
print("message_id:", message_id)
print("test code:", code)
