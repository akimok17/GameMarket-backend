from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _columns(engine: Engine, table: str) -> set[str]:
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def migrate_legacy_schema(engine: Engine) -> list[str]:
    """Add missing columns to legacy PostgreSQL tables without deleting user data."""
    if engine.dialect.name != "postgresql":
        return []

    changed: list[str] = []
    additions: dict[str, list[tuple[str, str]]] = {
        "users": [
            ("is_active", "BOOLEAN NOT NULL DEFAULT TRUE"),
            ("email_verified_at", "TIMESTAMPTZ NULL"),
            ("phone_verified_at", "TIMESTAMPTZ NULL"),
            ("last_login_at", "TIMESTAMPTZ NULL"),
            ("failed_login_attempts", "INTEGER NOT NULL DEFAULT 0"),
            ("locked_until", "TIMESTAMPTZ NULL"),
            ("token_version", "INTEGER NOT NULL DEFAULT 0"),
            ("withdrawable_balance", "NUMERIC(14,2) NOT NULL DEFAULT 0"),
        ],
        "products": [
            ("fulfillment_type", "VARCHAR(20) NOT NULL DEFAULT 'manual'"),
        ],
        "orders": [
            ("paid_at", "TIMESTAMPTZ NULL"),
            ("delivered_at", "TIMESTAMPTZ NULL"),
            ("cancelled_at", "TIMESTAMPTZ NULL"),
            ("settled_at", "TIMESTAMPTZ NULL"),
            ("delivery_secret", "TEXT NULL"),
            ("product_title_snapshot", "VARCHAR(200) NULL"),
            ("product_category_snapshot", "VARCHAR(50) NULL"),
            ("last_activity_at", "TIMESTAMPTZ NOT NULL DEFAULT NOW()"),
            ("buyer_withdrawable_spent", "NUMERIC(14,2) NOT NULL DEFAULT 0"),
        ],
        "balance_history": [
            ("reference_type", "VARCHAR(30) NULL"),
            ("reference_id", "INTEGER NULL"),
        ],
        "withdrawal_requests": [
            ("processed_by", "INTEGER NULL"),
            ("provider", "VARCHAR(32) NOT NULL DEFAULT 'manual'"),
            ("provider_payout_id", "VARCHAR(128) NULL"),
            ("idempotency_key", "VARCHAR(64) NULL"),
            ("bank_id", "VARCHAR(32) NULL"),
            ("failure_reason", "TEXT NULL"),
        ],
        "payment_deposits": [
            ("failure_reason", "TEXT NULL"),
            ("updated_at", "TIMESTAMPTZ NOT NULL DEFAULT NOW()"),
        ],
        # Some early GameMarket builds created `disputes` with a different
        # column set.  Order Room loads the ORM Dispute model, so every ORM
        # column has to exist even when the table itself already existed.
        "verification_codes": [
            ("provider", "VARCHAR(32) NULL"),
            ("provider_message_id", "VARCHAR(160) NULL"),
            ("sent_at", "TIMESTAMPTZ NULL"),
            ("request_ip", "VARCHAR(64) NULL"),
        ],
        "disputes": [
            ("initiator_id", "INTEGER NULL"),
            ("reason", "VARCHAR(100) NULL"),
            ("description", "TEXT NULL"),
            ("status", "VARCHAR(30) NULL DEFAULT 'open'"),
            ("resolution", "VARCHAR(20) NULL"),
            ("previous_order_status", "VARCHAR(20) NULL"),
            ("created_at", "TIMESTAMPTZ NULL DEFAULT NOW()"),
            ("resolved_at", "TIMESTAMPTZ NULL"),
            ("resolved_by", "INTEGER NULL"),
        ],
    }

    with engine.begin() as conn:
        for table, cols in additions.items():
            existing = _columns(engine, table)
            if not existing:
                continue
            for name, ddl in cols:
                if name not in existing:
                    conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {ddl}'))
                    changed.append(f"{table}.{name}")

        widen = [
            ("users", "balance"), ("users", "balance_frozen"), ("users", "withdrawable_balance"),
            ("products", "price"), ("products", "old_price"),
            ("orders", "total_price"), ("orders", "commission"), ("orders", "seller_earnings"), ("orders", "buyer_withdrawable_spent"),
            ("balance_history", "amount"), ("withdrawal_requests", "amount"), ("payment_deposits", "amount"),
        ]
        tables = set(inspect(engine).get_table_names())
        for table, column in widen:
            if table in tables and column in _columns(engine, table):
                conn.execute(text(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE NUMERIC(14,2)'))

        if "withdrawal_requests" in tables and "users" in tables:
            conn.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'fk_withdrawal_processed_by'
                    ) THEN
                        ALTER TABLE withdrawal_requests
                        ADD CONSTRAINT fk_withdrawal_processed_by
                        FOREIGN KEY (processed_by) REFERENCES users(id) ON DELETE SET NULL;
                    END IF;
                END $$;
            """))

        # Backfill/normalize legacy disputes so querying Order Room cannot fail
        # with UndefinedColumn and old disputes remain readable.
        if "disputes" in tables and "orders" in tables:
            conn.execute(text("""
                UPDATE disputes d
                SET initiator_id = o.buyer_id
                FROM orders o
                WHERE d.order_id = o.id AND d.initiator_id IS NULL
            """))
            conn.execute(text("""
                UPDATE disputes d
                SET previous_order_status = CASE
                    WHEN o.delivered_at IS NOT NULL OR o.delivery_info IS NOT NULL THEN 'delivered'
                    ELSE 'paid'
                END
                FROM orders o
                WHERE d.order_id = o.id AND d.previous_order_status IS NULL
            """))
            conn.execute(text("UPDATE disputes SET status='open' WHERE status IS NULL"))
            conn.execute(text("UPDATE disputes SET reason='Legacy dispute' WHERE reason IS NULL OR btrim(reason)=''"))
            conn.execute(text("UPDATE disputes SET created_at=NOW() WHERE created_at IS NULL"))

        if "disputes" in tables and "users" in tables:
            conn.execute(text("""
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
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_disputes_initiator_id ON disputes(initiator_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_disputes_status ON disputes(status)"))

        if "verification_codes" in tables:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_verification_codes_request_ip ON verification_codes(request_ip)"))

        if "payment_deposits" in tables:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_deposits_provider_payment_id ON payment_deposits(provider_payment_id) WHERE provider_payment_id IS NOT NULL"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_deposits_idempotency_key ON payment_deposits(idempotency_key)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_payment_deposits_user_created ON payment_deposits(user_id, created_at DESC)"))

        if "withdrawal_requests" in tables:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_withdrawal_provider_payout_id ON withdrawal_requests(provider_payout_id) WHERE provider_payout_id IS NOT NULL"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_withdrawal_idempotency_key ON withdrawal_requests(idempotency_key) WHERE idempotency_key IS NOT NULL"))

        if "users" in tables and "phone" in _columns(engine, "users"):
            duplicate_phone = conn.execute(text("""
                SELECT phone FROM users
                WHERE phone IS NOT NULL AND btrim(phone) <> ''
                GROUP BY phone HAVING COUNT(*) > 1 LIMIT 1
            """)).scalar()
            if duplicate_phone is None:
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_phone_not_null ON users(phone) WHERE phone IS NOT NULL"))
            else:
                print("[GameMarket] WARNING: duplicate phone values exist; unique phone index was not created")

    return changed
