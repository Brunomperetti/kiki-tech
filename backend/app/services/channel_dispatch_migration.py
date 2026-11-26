"""Opt-in DDL. Never invoked by startup or an API request."""

UP = (
    "CREATE TABLE public.kiki_channel_dispatch ("
    "id VARCHAR(36) PRIMARY KEY, "
    "channel VARCHAR(2) NOT NULL, "
    "store_id VARCHAR(64) NOT NULL, "
    "ecomm_id VARCHAR(64) NOT NULL, "
    "sku_key VARCHAR(256) NOT NULL, "
    "fingerprint VARCHAR(64) NOT NULL, "
    "actor VARCHAR(240) NOT NULL, "
    "state VARCHAR(16) NOT NULL, "
    "revision INTEGER NOT NULL, "
    "remote_id VARCHAR(64), "
    "created_at TIMESTAMPTZ NOT NULL, "
    "updated_at TIMESTAMPTZ NOT NULL, "
    "CONSTRAINT uq_dispatch_sku UNIQUE (channel, store_id, sku_key), "
    "CONSTRAINT uq_dispatch_identity UNIQUE (channel, store_id, ecomm_id), "
    "CONSTRAINT ck_dispatch_channel CHECK (channel IN ('tn', 'ml')), "
    "CONSTRAINT ck_dispatch_state CHECK "
    "(state IN ('RESERVED', 'IN_FLIGHT', 'CONFIRMED', 'UNKNOWN')))",
)

# Roll back code/flags first; retain all dispatch history, even UNKNOWN.
# DOWN is intentionally restricted to an empty table.
DOWN = (
    "DO $kiki_dispatch_down$ BEGIN "
    "LOCK TABLE public.kiki_channel_dispatch IN ACCESS EXCLUSIVE MODE; "
    "IF EXISTS (SELECT 1 FROM public.kiki_channel_dispatch LIMIT 1) THEN "
    "RAISE EXCEPTION 'KIKI_DISPATCH_DOWN_BLOCKED_NONEMPTY'; "
    "END IF; "
    "EXECUTE 'DROP TABLE public.kiki_channel_dispatch'; "
    "END $kiki_dispatch_down$",
)
