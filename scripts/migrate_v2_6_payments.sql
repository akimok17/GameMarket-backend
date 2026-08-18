BEGIN;

-- GameMarket v2.6.0: real deposits/payouts, withdrawable seller earnings,
-- idempotent provider references and exact refund source tracking.

ALTER TABLE IF EXISTS users
    ADD COLUMN IF NOT EXISTS withdrawable_balance NUMERIC(14,2) NOT NULL DEFAULT 0;

ALTER TABLE IF EXISTS orders
    ADD COLUMN IF NOT EXISTS buyer_withdrawable_spent NUMERIC(14,2) NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS payment_deposits (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    provider VARCHAR(32) NOT NULL DEFAULT 'yookassa',
    provider_payment_id VARCHAR(128),
    idempotency_key VARCHAR(64) NOT NULL,
    amount NUMERIC(14,2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'RUB',
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    confirmation_url TEXT,
    failure_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    succeeded_at TIMESTAMPTZ,
    canceled_at TIMESTAMPTZ,
    CONSTRAINT ck_payment_deposit_amount_positive CHECK (amount > 0)
);

-- If the table was created earlier from the preliminary snippet, complete it.
ALTER TABLE IF EXISTS payment_deposits
    ADD COLUMN IF NOT EXISTS failure_reason TEXT,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_deposits_provider_payment_id
    ON payment_deposits(provider_payment_id)
    WHERE provider_payment_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_deposits_idempotency_key
    ON payment_deposits(idempotency_key);
CREATE INDEX IF NOT EXISTS ix_payment_deposits_user_created
    ON payment_deposits(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_payment_deposits_status
    ON payment_deposits(status);

ALTER TABLE IF EXISTS withdrawal_requests
    ADD COLUMN IF NOT EXISTS provider VARCHAR(32) NOT NULL DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS provider_payout_id VARCHAR(128),
    ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(64),
    ADD COLUMN IF NOT EXISTS bank_id VARCHAR(32),
    ADD COLUMN IF NOT EXISTS failure_reason TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_withdrawal_provider_payout_id
    ON withdrawal_requests(provider_payout_id)
    WHERE provider_payout_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_withdrawal_idempotency_key
    ON withdrawal_requests(idempotency_key)
    WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_withdrawal_provider_status
    ON withdrawal_requests(provider, status);

-- Existing balances are intentionally NOT marked withdrawable automatically.
-- This is conservative: only seller earnings generated after this migration
-- become withdrawable. If you want to migrate historical seller earnings,
-- review balance_history manually and set users.withdrawable_balance explicitly.

COMMIT;
