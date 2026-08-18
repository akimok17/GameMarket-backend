-- GameMarket v2.3.0: Order Room migration.
-- Safe to run repeatedly. No existing orders/products/users are deleted.

BEGIN;


-- ---------------------------------------------------------------------------
-- Compatibility fix for legacy `disputes` tables.
-- Earlier builds could already have a disputes table with another column set;
-- CREATE TABLE/metadata.create_all does not add missing columns to that table.
-- ---------------------------------------------------------------------------
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

ALTER TABLE IF EXISTS orders ADD COLUMN IF NOT EXISTS delivery_secret TEXT NULL;
ALTER TABLE IF EXISTS orders ADD COLUMN IF NOT EXISTS product_title_snapshot VARCHAR(200) NULL;
ALTER TABLE IF EXISTS orders ADD COLUMN IF NOT EXISTS product_category_snapshot VARCHAR(50) NULL;
ALTER TABLE IF EXISTS orders ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
CREATE INDEX IF NOT EXISTS ix_orders_last_activity_at ON orders(last_activity_at);

-- Preserve what the buyer actually bought even if the seller edits the product later.
UPDATE orders o
SET product_title_snapshot = p.title
FROM products p
WHERE o.product_id = p.id AND o.product_title_snapshot IS NULL;

UPDATE orders o
SET product_category_snapshot = p.category
FROM products p
WHERE o.product_id = p.id AND o.product_category_snapshot IS NULL;

CREATE TABLE IF NOT EXISTS order_messages (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    message TEXT NULL,
    attachment_url VARCHAR(500) NULL,
    attachment_name VARCHAR(255) NULL,
    attachment_mime VARCHAR(100) NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    read_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_order_message_has_content CHECK (message IS NOT NULL OR attachment_url IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_order_messages_order_id ON order_messages(order_id);
CREATE INDEX IF NOT EXISTS ix_order_messages_sender_id ON order_messages(sender_id);
CREATE INDEX IF NOT EXISTS ix_order_messages_is_read ON order_messages(is_read);
CREATE INDEX IF NOT EXISTS ix_order_messages_created_at ON order_messages(created_at);
CREATE INDEX IF NOT EXISTS ix_order_messages_order_created ON order_messages(order_id, created_at);

CREATE TABLE IF NOT EXISTS order_events (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    actor_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
    event_type VARCHAR(40) NOT NULL,
    text VARCHAR(500) NOT NULL,
    payload JSON NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_order_events_order_id ON order_events(order_id);
CREATE INDEX IF NOT EXISTS ix_order_events_actor_id ON order_events(actor_id);
CREATE INDEX IF NOT EXISTS ix_order_events_event_type ON order_events(event_type);
CREATE INDEX IF NOT EXISTS ix_order_events_created_at ON order_events(created_at);
CREATE INDEX IF NOT EXISTS ix_order_events_order_created ON order_events(order_id, created_at);

-- Give old orders a useful timeline. NOT EXISTS keeps this migration repeatable.
INSERT INTO order_events(order_id, actor_id, event_type, text, created_at)
SELECT o.id, o.buyer_id, 'created', 'Заказ создан', o.created_at
FROM orders o
WHERE NOT EXISTS (SELECT 1 FROM order_events e WHERE e.order_id=o.id AND e.event_type='created');

INSERT INTO order_events(order_id, actor_id, event_type, text, created_at)
SELECT o.id, o.buyer_id, 'paid', 'Покупатель оплатил заказ. Средства помещены в резерв сделки.', o.paid_at
FROM orders o
WHERE o.paid_at IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM order_events e WHERE e.order_id=o.id AND e.event_type='paid');

INSERT INTO order_events(order_id, actor_id, event_type, text, created_at)
SELECT o.id, o.seller_id, 'delivered', 'Товар передан покупателю.', o.delivered_at
FROM orders o
WHERE o.delivered_at IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM order_events e WHERE e.order_id=o.id AND e.event_type='delivered');

INSERT INTO order_events(order_id, actor_id, event_type, text, created_at)
SELECT o.id, o.buyer_id, 'completed', 'Сделка завершена.', o.completed_at
FROM orders o
WHERE o.completed_at IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM order_events e WHERE e.order_id=o.id AND e.event_type IN ('confirmed','completed','auto_completed'));

INSERT INTO order_events(order_id, actor_id, event_type, text, created_at)
SELECT o.id, o.buyer_id, 'cancelled', 'Заказ отменён.', COALESCE(o.cancelled_at, o.created_at)
FROM orders o
WHERE o.status='cancelled'
  AND NOT EXISTS (SELECT 1 FROM order_events e WHERE e.order_id=o.id AND e.event_type='cancelled');

COMMIT;
