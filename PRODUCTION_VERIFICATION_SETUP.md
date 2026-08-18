# GameMarket v2.5.0 — production verification

## Architecture

Web and Android never send email/SMS themselves. They call the same FastAPI endpoints:

- `GET /verification/public-config`
- `GET /verification/status` (authorized)
- `POST /verification/request` (authorized account verification)
- `POST /verification/confirm`
- `POST /users/password-reset/request` (public)
- `POST /users/password-reset/confirm` (public)

All provider secrets exist only in backend `.env` on the server.

## What users can do

1. Register with personal email and optional phone.
2. Verify email: code is delivered to the email stored in their account.
3. Verify phone: code is delivered by SMS to the phone stored in their account.
4. If email/phone is changed, verification for that contact is reset.
5. Recover password by either email or SMS, depending on configured channels.
6. Password reset revokes previous JWT sessions.

## Verification policy

Available values: `none`, `any`, `email`, `phone`, `both`.

Example marketplace policy:

```env
REQUIRE_VERIFIED_FOR_SELLING=true
REQUIRE_VERIFIED_FOR_WITHDRAWAL=true
SELLER_VERIFICATION_POLICY=any
WITHDRAWAL_VERIFICATION_POLICY=both
PASSWORD_RESET_CHANNELS=email,phone
```

If you want BOTH email and phone before seller mode, use:

```env
SELLER_VERIFICATION_POLICY=both
```

## Email

One GameMarket sender mailbox sends to every user's personal mailbox.

Example Mail.ru sender:

```env
SMTP_HOST=smtp.mail.ru
SMTP_PORT=465
SMTP_USERNAME=no-reply@your-domain-or-mailbox.ru
SMTP_PASSWORD=APPLICATION_PASSWORD
SMTP_FROM_EMAIL=no-reply@your-domain-or-mailbox.ru
SMTP_FROM_NAME=GameMarket
SMTP_SECURITY=ssl
SMTP_TIMEOUT_SECONDS=30
SMTP_TLS_VERSION=auto
```

If your local VPN/proxy causes TLS negotiation errors but forced TLS 1.2 works, use `SMTP_TLS_VERSION=tls1_2`. On a normal VPS try `auto` first.

For a domain sender, configure SPF, DKIM and DMARC with the mail provider/DNS host to improve deliverability.

## SMS.RU

```env
SMS_PROVIDER=smsru
SMSRU_API_ID=YOUR_API_ID
SMSRU_FROM=
```

`SMSRU_FROM` can remain empty until a sender name is approved. Backend passes the requesting IP to SMS.RU when available and also has its own rate limits.

## Anti-abuse

```env
VERIFICATION_CODE_TTL_MINUTES=10
VERIFICATION_RESEND_SECONDS=60
VERIFICATION_MAX_ATTEMPTS=5
VERIFICATION_MAX_SENDS_PER_HOUR=5
VERIFICATION_MAX_SENDS_PER_IP_HOUR=20
OTP_DEV_ECHO=false
```

Codes are stored as HMAC hashes, not plaintext. Public password-reset request returns a generic response so it does not directly reveal whether an account exists.

## Existing database

Run once in pgAdmin:

```text
scripts/migrate_v2_5.sql
```

or temporarily set `MIGRATE_LEGACY_SCHEMA=true` for one startup.

## Recommended production `.env`

```env
ENVIRONMENT=production
DATABASE_URL=postgresql://USER:STRONG_PASSWORD@127.0.0.1:5432/marketplace
SECRET_KEY=LONG_RANDOM_SECRET_32+_CHARS
CONTENT_ENCRYPTION_KEY=FERNET_KEY
ACCESS_TOKEN_EXPIRE_MINUTES=1440
ALLOW_DEV_DEPOSITS=false
OTP_DEV_ECHO=false
CREATE_TABLES_ON_STARTUP=true
MIGRATE_LEGACY_SCHEMA=false

PUBLIC_APP_URL=https://gamemarket.example
CORS_ORIGINS=https://gamemarket.example

REQUIRE_VERIFIED_FOR_SELLING=true
REQUIRE_VERIFIED_FOR_WITHDRAWAL=true
SELLER_VERIFICATION_POLICY=any
WITHDRAWAL_VERIFICATION_POLICY=both
PASSWORD_RESET_CHANNELS=email,phone

SMTP_HOST=...
SMTP_PORT=...
SMTP_USERNAME=...
SMTP_PASSWORD=...
SMTP_FROM_EMAIL=...
SMTP_FROM_NAME=GameMarket
SMTP_SECURITY=ssl
SMTP_TLS_VERSION=auto

SMS_PROVIDER=smsru
SMSRU_API_ID=...
```

Put FastAPI behind HTTPS reverse proxy (Nginx/Caddy) and use `https://api.your-domain/...` from the Android release build.
