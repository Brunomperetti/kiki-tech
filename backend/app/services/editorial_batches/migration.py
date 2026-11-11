"""Explicit UP/DOWN; invoked only after disposable PostgreSQL preflight in 2Q.

No automatic production DDL. Export coordination/history before any future DOWN.
Proposals and commercial records remain in their existing tables.
"""

UP = (
    "CREATE TABLE kiki_editorial_batches (id VARCHAR(36) PRIMARY KEY, request_key VARCHAR(80) NOT NULL UNIQUE, operation VARCHAR(30) NOT NULL, state VARCHAR(20) NOT NULL, revision INTEGER NOT NULL, created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL, creator VARCHAR(240) NOT NULL, authorized_by VARCHAR(240), authorized_at TIMESTAMPTZ, start_key VARCHAR(80), selection JSON NOT NULL, summary JSON NOT NULL, preview_hash VARCHAR(64) NOT NULL, total INTEGER NOT NULL, owner VARCHAR(36), lease_until TIMESTAMPTZ, history JSON NOT NULL)",
    "CREATE TABLE kiki_editorial_batch_items (id VARCHAR(36) PRIMARY KEY, batch_id VARCHAR(36) NOT NULL REFERENCES kiki_editorial_batches(id) ON DELETE CASCADE, ecomm_id VARCHAR(120) NOT NULL, position INTEGER NOT NULL, state VARCHAR(20) NOT NULL, attempts INTEGER NOT NULL, expected JSON NOT NULL, result JSON NOT NULL, error JSON NOT NULL, history JSON NOT NULL, UNIQUE(batch_id,ecomm_id), UNIQUE(batch_id,position))",
    "CREATE INDEX kiki_editorial_items_state ON kiki_editorial_batch_items(batch_id,state,position)",
    "CREATE INDEX kiki_editorial_batches_created ON kiki_editorial_batches(created_at)",
)
DOWN = ("DROP TABLE kiki_editorial_batch_items", "DROP TABLE kiki_editorial_batches")
