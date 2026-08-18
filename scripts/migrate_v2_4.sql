BEGIN;
ALTER TABLE IF EXISTS verification_codes ADD COLUMN IF NOT EXISTS provider VARCHAR(32);
ALTER TABLE IF EXISTS verification_codes ADD COLUMN IF NOT EXISTS provider_message_id VARCHAR(160);
ALTER TABLE IF EXISTS verification_codes ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ;
UPDATE verification_codes SET sent_at=created_at WHERE sent_at IS NULL AND created_at IS NOT NULL;
COMMIT;
