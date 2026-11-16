"""PostgreSQL 18 disposable migration check for GitHub Actions only.

No credentials, production snapshots, providers, file uploads or external writes.
The entire database exists only within the CI job's ephemeral Postgres service.
"""
import os

if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("KIKI_CI_SYNTHETIC_ONLY") != "1":
    raise SystemExit("The migration smoke may only run in explicitly opted-in GitHub CI.")

import psycopg  # noqa: E402

from app.services.v2_schema import statements  # noqa: E402


def main():
    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="kiki_ci_synthetic",
        user="kiki_ci",
        password="synthetic_ci_only",
        connect_timeout=5,
    ) as db:
        database, actor = db.execute("SELECT current_database(), current_user").fetchone()
        assert (database, actor) == ("kiki_ci_synthetic", "kiki_ci")
        db.execute("SET LOCAL lock_timeout = '5s'")
        db.execute("CREATE TABLE ci_legacy_guard (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("INSERT INTO ci_legacy_guard VALUES (1, 'untouched')")

        # A partially-installed schema must refuse migration rather than guessing.
        db.execute("CREATE TABLE kiki_evidence_control (id INTEGER PRIMARY KEY)")
        try:
            with db.transaction():  # savepoint; the failed DO cannot abort outer checks
                for statement in statements():
                    db.execute(statement)
        except psycopg.Error as exc:
            if "Esquema parcial" not in str(exc):
                raise
        else:
            raise AssertionError("Partial schema was not rejected")
        db.execute("DROP TABLE kiki_evidence_control")

        for _ in range(2):  # explicit migration must be idempotent
            for statement in statements():
                db.execute(statement)

        names = (
            "kiki_evidence_control",
            "kiki_evidence_documents",
            "kiki_evidence_dossiers",
            "kiki_editorial_batches",
            "kiki_editorial_batch_items",
            "kiki_editorial_batch_signals",
        )
        for name in names:
            assert db.execute("SELECT to_regclass(%s)", (f"public.{name}",)).fetchone()[0], name
        assert db.execute("SELECT id FROM kiki_evidence_control").fetchall() == [(1,)]
        assert db.execute("SELECT id, value FROM ci_legacy_guard").fetchall() == [(1, "untouched")]
        db.rollback()
    print("Disposable PostgreSQL 18: additive SQL, partial rejection and legacy guard PASS")


if __name__ == "__main__":
    main()
