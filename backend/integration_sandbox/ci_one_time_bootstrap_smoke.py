"""Only disposable PostgreSQL18 verifies the exact opt-in Render boot path."""
import os

if (
    os.environ.get("GITHUB_ACTIONS") != "true"
    or os.environ.get("KIKI_CI_SYNTHETIC_ONLY") != "1"
):
    raise SystemExit("Only the ephemeral synthetic GitHub Actions database is permitted")

from sqlalchemy import create_engine, text  # noqa: E402
from app.services.documental import one_time_bootstrap as bootstrap  # noqa: E402


def main():
    engine = create_engine(
        "postgresql+psycopg://kiki_ci:synthetic_ci_only@127.0.0.1:5432/kiki_ci_synthetic",
        connect_args={"connect_timeout": 5},
    )
    bootstrap.TARGET_DATABASE = "kiki_ci_synthetic"
    # Source and editorial tables are untouched, including rows present
    # before the six new schema objects are installed.
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE catalog_snapshots (id INTEGER PRIMARY KEY, marker TEXT)"
        ))
        connection.execute(text(
            "CREATE TABLE ecomm_api_product_edits (id INTEGER PRIMARY KEY, marker TEXT)"
        ))
        connection.execute(text(
            "INSERT INTO catalog_snapshots VALUES (1, 'legacy-content-unchanged')"
        ))
        connection.execute(text(
            "INSERT INTO ecomm_api_product_edits VALUES (1, 'editor-content-unchanged')"
        ))
    # Wrong expected database refuses DDL even though it has a connection.
    try:
        bootstrap.apply_additive_schema(engine, expected_database="wrong_db")
    except ValueError as exc:
        assert "no autorizado" in str(exc)
    else:
        raise AssertionError("Wrong database was allowed")

    # A partial existing group must fail and roll back the transaction.
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE kiki_evidence_control (id INTEGER PRIMARY KEY)"
        ))
    try:
        bootstrap.apply_additive_schema(
            engine, expected_database="kiki_ci_synthetic",
        )
    except Exception as exc:
        assert "Esquema parcial" in str(exc)
    else:
        raise AssertionError("Partial group was allowed")
    with engine.begin() as connection:
        assert connection.execute(text(
            "SELECT to_regclass('public.kiki_evidence_documents')"
        )).scalar_one() is None
        connection.execute(text("DROP TABLE kiki_evidence_control"))

    # Idempotent on second startup; never re-create, drop or edit core rows.
    for _ in range(2):
        outcome = bootstrap.apply_additive_schema(
            engine, expected_database="kiki_ci_synthetic",
        )
        assert outcome == {"schema_verified": True, "tables": 6}
    with engine.connect() as connection:
        for name, marker in [
            ("catalog_snapshots", "legacy-content-unchanged"),
            ("ecomm_api_product_edits", "editor-content-unchanged"),
        ]:
            assert connection.execute(
                text(f"SELECT marker FROM {name} WHERE id=1")
            ).scalar_one() == marker
        installed = connection.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='public' AND ("
            "table_name LIKE 'kiki_evidence_%' OR "
            "table_name LIKE 'kiki_editorial_%')"
        )).scalar_one()
        assert installed == 6
    engine.dispose()
    print("PASS: exact gated startup migration; atomic, idempotent, preserves legacy")


if __name__ == "__main__":
    main()
