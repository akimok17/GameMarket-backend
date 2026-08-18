-- GameMarket v2.3.1 hotfix: make a legacy disputes table compatible with Order Room.
-- Safe to run repeatedly. Existing disputes/orders/users are not deleted.
BEGIN;

ALTER TABLE IF EXISTS disputes ADD COLUMN IF NOT EXISTS initiator_id INTEGER NULL;
ALTER TABLE IF EXISTS disputes ADD COLUMN IF NOT EXISTS reason VARCHAR(100) NULL;
ALTER TABLE IF EXISTS disputes ADD COLUMN IF NOT EXISTS description TEXT NULL;
ALTER TABLE IF EXISTS disputes ADD COLUMN IF NOT EXISTS status VARCHAR(30) NULL DEFAULT 'open';
ALTER TABLE IF EXISTS disputes ADD COLUMN IF NOT EXISTS resolution VARCHAR(20) NULL;
ALTER TABLE IF EXISTS disputes ADD COLUMN IF NOT EXISTS previous_order_status VARCHAR(20) NULL;
ALTER TABLE IF EXISTS disputes ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NULL DEFAULT NOW();
ALTER TABLE IF EXISTS disputes ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ NULL;
ALTER TABLE IF EXISTS disputes ADD COLUMN IF NOT EXISTS resolved_by INTEGER NULL;

UPDATE disputes d
SET initiator_id = o.buyer_id
FROM orders o
WHERE d.order_id = o.id AND d.initiator_id IS NULL;

UPDATE disputes d
SET previous_order_status = CASE
    WHEN o.delivered_at IS NOT NULL OR o.delivery_info IS NOT NULL THEN 'delivered'
    ELSE 'paid'
END
FROM orders o
WHERE d.order_id = o.id AND d.previous_order_status IS NULL;

UPDATE disputes SET status = 'open' WHERE status IS NULL;
UPDATE disputes SET reason = 'Legacy dispute' WHERE reason IS NULL OR btrim(reason) = '';
UPDATE disputes SET created_at = NOW() WHERE created_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_disputes_initiator_id ON disputes(initiator_id);
CREATE INDEX IF NOT EXISTS ix_disputes_status ON disputes(status);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_disputes_initiator') THEN
        ALTER TABLE disputes ADD CONSTRAINT fk_disputes_initiator
        FOREIGN KEY (initiator_id) REFERENCES users(id) ON DELETE RESTRICT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_disputes_resolved_by') THEN
        ALTER TABLE disputes ADD CONSTRAINT fk_disputes_resolved_by
        FOREIGN KEY (resolved_by) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
END $$;

COMMIT;
