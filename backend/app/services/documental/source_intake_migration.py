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
# Fail-closed DOWN: a single SQL statement holds an ACCESS EXCLUSIVE lock
# across both the nonempty check and DROP, even with autocommit enabled.
# Production rollback is normally CODE/FLAGS ONLY: retain this table and
# its operator history. Run DOWN solely with separate approval and after
# proving it is empty. Never truncate/delete rows to make DOWN pass.
DOWN = (
    "DO $kiki_intake_down$ BEGIN "
    "LOCK TABLE public.kiki_source_intake_jobs IN ACCESS EXCLUSIVE MODE; "
    "IF EXISTS (SELECT 1 FROM public.kiki_source_intake_jobs LIMIT 1) THEN "
    "RAISE EXCEPTION 'KIKI_INTAKE_DOWN_BLOCKED_NONEMPTY: conservar historial'; "
    "END IF; "
    "EXECUTE 'DROP TABLE public.kiki_source_intake_jobs'; "
    "END $kiki_intake_down$",
)
