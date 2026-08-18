# v2.5.0 account verification changes

- Email and phone verification use the same backend flow for web + Android.
- Password recovery supports both email and SMS.
- Backward compatibility kept for old clients that send `{ "email": "..." }` to password reset.
- New clients send `{ "identifier": "...", "channel": "email|phone" }`.
- Seller and withdrawal verification are configurable independently: `any`, `email`, `phone`, `both`, `none`.
- Added public provider config endpoint for login/reset screens.
- Added per-IP OTP rate limit and request IP storage.
- SMS.RU requests include requester IP when available.
- Fixed SMTP TLS version context: `SMTP_TLS_VERSION=tls1_2` is now actually applied.
- Changing email or phone invalidates verification for only that changed contact.
- Successful password reset revokes existing sessions and consumes remaining reset codes.
