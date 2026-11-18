"""Opt-in additive migration for the source-intake coordination row.

Never executed on FastAPI startup. Run first in disposable PostgreSQL 18 and
confirm a restorable backup before any later production deployment.
"""
UP = (
    "CREATE TABLE kiki_source_intake_jobs ("
    "id VARCHAR(36) PRIMARY KEY, "
    "request_key VARCHAR(36) NOT NULL UNIQUE, "
    "created_at TIMESTAMPTZ NOT NULL, "
    "updated_at TIMESTAMPTZ NOT NULL, "
    "creator VARCHAR(240) NOT NULL, "
    "revision INTEGER NOT NULL, "
    "state VARCHAR(24) NOT NULL, "
    "sitemap_url VARCHAR(1000) NOT NULL, "
    "sitemap_sha256 VARCHAR(64) NOT NULL, "
    "source_host VARCHAR(253) NOT NULL, "
    "items JSON NOT NULL, "
    "history JSON NOT NULL)",
    "CREATE INDEX kiki_source_intake_created_idx "
    "ON kiki_source_intake_jobs(created_at DESC)",
)
# Dropping coordination would delete operator history. Export and require an
# empty table, with explicit approval, before any DOWN.
DOWN = (
    "DROP INDEX kiki_source_intake_created_idx",
    "DROP TABLE kiki_source_intake_jobs",
)
