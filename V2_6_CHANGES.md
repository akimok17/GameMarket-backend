# GameMarket v2.6.0 — payments, payouts and phone verification

## Payments

- Real YooKassa balance deposits are created only by the backend.
- Deposit records use a unique idempotency key and provider payment id.
- User balance is credited only after the backend re-reads the authoritative YooKassa payment and sees `succeeded` + `paid=true` with the exact expected RUB amount.
- Repeated webhooks/status syncs cannot credit the same deposit twice.
- Web and Android share the same deposit API and history.
- Android browser checkout returns to the HTTPS `/payment-return` bridge page; the app also syncs the last deposit on resume.

## Withdrawals

- Added a separate `withdrawable_balance`: user top-ups are spendable, but only seller earnings become withdrawable.
- When withdrawable earnings are spent on a purchase, the exact withdrawable portion is tracked on the order so dispute refunds can restore the correct source.
- Withdrawal requests reserve funds first.
- YooKassa payout mode supports SBP, requires the account's verified phone, requires bank selection, and keeps payout destination encrypted at rest.
- Admin approval remains before the external payout as an anti-fraud checkpoint.
- Provider status is synchronized and `succeeded`/`canceled` webhooks are re-verified against YooKassa before balances change.

## Verification and UI

- Existing email/phone OTP backend flow is retained and production SMS.RU/Twilio/generic delivery is supported.
- Android Security screen can add a missing phone and immediately request SMS verification.
- Web and Android finance screens were reworked for real deposits/withdrawals and narrow-screen button layouts.

## Database

Run `scripts/migrate_v2_6_payments.sql` once on an existing PostgreSQL database. The migration is repeatable and also completes a preliminary `payment_deposits` table if you already created it manually.
