"""PostgreSQL 18 smoke for the optional manufacturer-intake migration.

Runs ONLY inside GitHub's disposable postgres service. Never accesses
Render, tenant DB, provider credentials or product data.
"""
import os

if (
    os.environ.get("GITHUB_ACTIONS") != "true"
    or os.environ.get("KIKI_CI_SYNTHETIC_ONLY") != "1"
):
    raise SystemExit("Only CI disposable PostgreSQL may run this migration smoke.")

import psycopg  # noqa: E402
from app.services.documental.source_intake_migration import UP, DOWN  # noqa: E402
from app.services.documental.source_intake_storage import SourceIntakeJob  # noqa: E402


def main():
    with psycopg.connect(
        host="127.0.0.1", port=5432, dbname="kiki_ci_synthetic",
        user="kiki_ci", password="synthetic_ci_only", connect_timeout=5,
    ) as db:
        assert db.execute(
            "SELECT current_database(), current_user"
        ).fetchone() == ("kiki_ci_synthetic", "kiki_ci")
        db.execute("SET LOCAL lock_timeout = '5s'")
        db.execute("CREATE TABLE ci_intake_guard (id INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO ci_intake_guard VALUES (1)")
        for sql in UP:
            db.execute(sql)
        cols = {
            row[0]
            for row in db.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='kiki_source_intake_jobs'"
            )
        }
        expected = {col.name for col in SourceIntakeJob.__table__.columns}
        assert cols == expected, (cols, expected)
        db.execute(
            "INSERT INTO kiki_source_intake_jobs "
            "(id, request_key, created_at, updated_at, creator, revision, "
            "state, sitemap_url, sitemap_sha256, source_host, items, history) "
            "VALUES (%s,%s,now(),now(),%s,1,'PENDING',%s,%s,%s,%s::json,%s::json)",
            (
                "00000000-0000-4000-8000-000000000001",
                "00000000-0000-4000-8000-000000000002",
                "synthetic-operator",
                "https://fabricante-prueba.invalid/product-sitemap.xml",
                "a" * 64,
                "fabricante-prueba.invalid",
                '[{"ecomm_id":"123","state":"PENDING"}]',
                '[{"action":"CREATED"}]',
            ),
        )
        assert db.execute(
            "SELECT revision, items->0->>'state' FROM kiki_source_intake_jobs"
        ).fetchone() == (1, "PENDING")
        # Commit a fake job, then reopen: this tests real durability on PG18.
        db.commit()
    with psycopg.connect(
        host="127.0.0.1", port=5432, dbname="kiki_ci_synthetic",
        user="kiki_ci", password="synthetic_ci_only", connect_timeout=5,
    ) as db:
        assert db.execute(
            "SELECT revision, items->0->>'state' FROM kiki_source_intake_jobs"
        ).fetchone() == (1, "PENDING")
        db.execute("SET LOCAL lock_timeout = '5s'")
        # Never destroy a queued job. A savepoint ensures the failed DO does
        # not abort the rest of the isolated test transaction.
        try:
            with db.transaction():
                for sql in DOWN:
                    db.execute(sql)
        except psycopg.Error as exc:
            assert "KIKI_INTAKE_DOWN_BLOCKED_NONEMPTY" in str(exc), str(exc)
        else:
            raise AssertionError("DOWN unexpectedly removed a nonempty queue")
        assert db.execute(
            "SELECT COUNT(*) FROM public.kiki_source_intake_jobs"
        ).fetchone()[0] == 1
        assert db.execute(
            "SELECT COUNT(*) FROM ci_intake_guard"
        ).fetchone()[0] == 1
        # Verify empty-only DOWN after explicitly removing only the synthetic
        # row. This is a CI fixture cleanup, never a production procedure.
        db.execute("DELETE FROM public.kiki_source_intake_jobs")
        for sql in DOWN:
            db.execute(sql)
        assert db.execute(
            "SELECT to_regclass('public.kiki_source_intake_jobs')"
        ).fetchone()[0] is None
        assert db.execute(
            "SELECT COUNT(*) FROM ci_intake_guard"
        ).fetchone()[0] == 1
        db.commit()
    print("Disposable PG18 source intake: durable JSON, blocked nonempty DOWN, "
          "empty-only rollback and legacy guard PASS")


if __name__ == "__main__":
    main()
