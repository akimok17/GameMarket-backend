-- GameMarket v2.2.0 migration for an existing PostgreSQL database.
-- Safe to run repeatedly. Existing users/products/orders are not deleted.

BEGIN;

ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ NULL;
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS phone_verified_at TIMESTAMPTZ NULL;
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ NULL;
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ NULL;
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0;

ALTER TABLE IF EXISTS products ADD COLUMN IF NOT EXISTS fulfillment_type VARCHAR(20) NOT NULL DEFAULT 'manual';

ALTER TABLE IF EXISTS orders ADD COLUMN IF NOT EXISTS paid_at TIMESTAMPTZ NULL;
ALTER TABLE IF EXISTS orders ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ NULL;
ALTER TABLE IF EXISTS orders ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ NULL;
ALTER TABLE IF EXISTS orders ADD COLUMN IF NOT EXISTS settled_at TIMESTAMPTZ NULL;

ALTER TABLE IF EXISTS balance_history ADD COLUMN IF NOT EXISTS reference_type VARCHAR(30) NULL;
ALTER TABLE IF EXISTS balance_history ADD COLUMN IF NOT EXISTS reference_id INTEGER NULL;
ALTER TABLE IF EXISTS withdrawal_requests ADD COLUMN IF NOT EXISTS processed_by INTEGER NULL;

CREATE TABLE IF NOT EXISTS verification_codes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel VARCHAR(10) NOT NULL,
    purpose VARCHAR(30) NOT NULL DEFAULT 'verify_account',
    destination VARCHAR(255) NOT NULL,
    code_hash VARCHAR(64) NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS ix_verification_user_channel_purpose ON verification_codes(user_id, channel, purpose);
CREATE INDEX IF NOT EXISTS ix_verification_codes_expires_at ON verification_codes(expires_at);

CREATE TABLE IF NOT EXISTS support_tickets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    subject VARCHAR(160) NOT NULL,
    category VARCHAR(40) NOT NULL DEFAULT 'general',
    priority VARCHAR(20) NOT NULL DEFAULT 'normal',
    status VARCHAR(30) NOT NULL DEFAULT 'open',
    order_id INTEGER NULL REFERENCES orders(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS ix_support_tickets_user_id ON support_tickets(user_id);
CREATE INDEX IF NOT EXISTS ix_support_tickets_status ON support_tickets(status);
CREATE INDEX IF NOT EXISTS ix_support_tickets_updated_at ON support_tickets(updated_at);

CREATE TABLE IF NOT EXISTS support_messages (
    id SERIAL PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
    author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    message TEXT NOT NULL,
    is_staff BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_support_messages_ticket_id ON support_messages(ticket_id);

CREATE TABLE IF NOT EXISTS market_notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR(40) NOT NULL DEFAULT 'info',
    title VARCHAR(160) NOT NULL,
    body TEXT NULL,
    link VARCHAR(255) NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_market_notifications_user_id ON market_notifications(user_id);
CREATE INDEX IF NOT EXISTS ix_market_notifications_unread ON market_notifications(user_id, is_read);

COMMIT;
