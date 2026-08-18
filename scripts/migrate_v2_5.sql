BEGIN;

ALTER TABLE IF EXISTS verification_codes
    ADD COLUMN IF NOT EXISTS request_ip VARCHAR(64);

CREATE INDEX IF NOT EXISTS ix_verification_codes_request_ip
    ON verification_codes(request_ip);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT phone FROM users
        WHERE phone IS NOT NULL AND btrim(phone) <> ''
        GROUP BY phone HAVING COUNT(*) > 1
    ) THEN
        CREATE UNIQUE INDEX IF NOT EXISTS uq_users_phone_not_null
            ON users(phone) WHERE phone IS NOT NULL;
    ELSE
        RAISE NOTICE 'Duplicate phone values exist. Unique phone index was not created.';
    END IF;
END $$;

COMMIT;
