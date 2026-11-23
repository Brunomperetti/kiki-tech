"""One-time intake release: real PostgreSQL 18, disposable CI only.

The exact same function runs behind the Render supervisor release token.
No real KIKI records, provider calls, secrets or Render network access.
"""
import os

if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("KIKI_CI_SYNTHETIC_ONLY") != "1":
    raise SystemExit("PG18 intake release smoke sólo en la base sintética descartable CI.")

from sqlalchemy import create_engine, text  # noqa: E402

from app.services.documental.intake_release_20261123 import migrate_once  # noqa: E402


def main():
    engine = create_engine(
        "postgresql+psycopg://kiki_ci:synthetic_ci_only@127.0.0.1:5432/kiki_ci_synthetic",
        connect_args={"connect_timeout": 5},
    )
    with engine.connect() as connection:
        assert connection.execute(text("SELECT current_database()")).scalar_one() == "kiki_ci_synthetic"
        assert connection.execute(text(
            "SELECT to_regclass('public.kiki_source_intake_jobs')"
        )).scalar_one() is None
        original = {
            name: connection.execute(text("SELECT count(*) FROM " + name)).scalar_one()
            for name in (
                "public.catalog_snapshots",
                "public.ecomm_api_product_edits",
                "public.kiki_evidence_documents",
                "public.kiki_evidence_dossiers",
                "public.kiki_editorial_batches",
            )
        }
    try:
        migrate_once(engine, expected_database="kiki_tech_db")
    except ValueError as exc:
        assert "nombre, versión" in str(exc)
    else:
        raise AssertionError("Wrong target DB accepted")
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT to_regclass('public.kiki_source_intake_jobs')"
        )).scalar_one() is None
    first = migrate_once(engine, expected_database="kiki_ci_synthetic")
    assert first == {"created": True, "table": "public.kiki_source_intake_jobs", "columns": 12}
    repeat = migrate_once(engine, expected_database="kiki_ci_synthetic")
    assert repeat == {"created": False, "table": "public.kiki_source_intake_jobs", "columns": 12}
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT count(*) FROM public.kiki_source_intake_jobs"
        )).scalar_one() == 0
        for name, count in original.items():
            assert connection.execute(text("SELECT count(*) FROM " + name)).scalar_one() == count
    engine.dispose()
    print("PG18 intake release PASS: transaction, target guard, 12 columns, idempotence, original rows preserved")


if __name__ == "__main__":
    main()
