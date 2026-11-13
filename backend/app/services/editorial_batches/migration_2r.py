"""Explicit additive disposable migration. No production startup DDL.

DOWN requires no PREPARING/PENDING/RUNNING jobs. Export signals before reversal.
Preserves all 2Q batches, items, documents, proposals and commercial records.
"""

UP = (
    "CREATE TABLE kiki_editorial_batch_signals (batch_id VARCHAR(36) PRIMARY KEY REFERENCES kiki_editorial_batches(id) ON DELETE CASCADE, requested_at TIMESTAMPTZ NOT NULL, requested_by VARCHAR(240) NOT NULL)",
    "CREATE INDEX kiki_editorial_active_identity ON kiki_editorial_batch_items(ecomm_id, state, batch_id)",
    "CREATE INDEX kiki_editorial_claimable ON kiki_editorial_batches(state, lease_until, updated_at)",
)
DOWN = (
    "DROP TABLE kiki_editorial_batch_signals",
    "DROP INDEX kiki_editorial_active_identity",
    "DROP INDEX kiki_editorial_claimable",
)
