# Реальная доставка OTP

Сайт и Android используют одинаковые backend-endpoints: `/verification/request` и `/verification/confirm`. SMTP/SMS секреты хранятся только в `.env` backend.

## Yandex SMTP
```env
OTP_DEV_ECHO=false
SMTP_HOST=smtp.yandex.com
SMTP_PORT=465
SMTP_USERNAME=your-mail@yandex.ru
SMTP_PASSWORD=APP_PASSWORD
SMTP_FROM_EMAIL=your-mail@yandex.ru
SMTP_FROM_NAME=GameMarket
SMTP_SECURITY=ssl
```

## SMS.RU
```env
SMS_PROVIDER=smsru
SMSRU_API_ID=YOUR_API_ID
SMSRU_FROM=
```

## Twilio
```env
SMS_PROVIDER=twilio
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM=+1...
# OR TWILIO_MESSAGING_SERVICE_SID=MG...
```

Перед запуском на существующей PostgreSQL выполнить `scripts/migrate_v2_4.sql`. Затем `GET /verification/providers` должен показать оба канала configured=true.


## Mail.ru + Python/OpenSSL: SSLEOFError / SMTPServerDisconnected

If `curl.exe -v smtps://smtp.mail.ru:465` connects but Python `SMTP_SSL` fails with
`ssl.SSLEOFError: UNEXPECTED_EOF_WHILE_READING`, test TLS 1.2. If TLS 1.2 works, set:

```env
SMTP_HOST=smtp.mail.ru
SMTP_PORT=465
SMTP_SECURITY=ssl
SMTP_TLS_VERSION=tls1_2
SMTP_TIMEOUT_SECONDS=30
```

This keeps certificate verification enabled; it only pins the SMTP TLS protocol to TLS 1.2.
`SMTP_TLS_VERSION=auto` remains the default for normal networks.
