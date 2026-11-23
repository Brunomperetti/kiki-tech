"""Single-use, operator-approved, additive intake table release for KIKI PG18.

Never enabled by default. No supplier calls, scheduled work, credentials,
product edits, deletions, or schema changes outside the new coordination table.
The supervisor invokes this only for the exact opt-in release token.
"""
from sqlalchemy import text

from app.services.documental.source_intake_migration import UP
from app.services.documental.source_intake_storage import SourceIntakeJob

TARGET_DB = "kiki_tech_db"
EXPECTED_TABLE = "public.kiki_source_intake_jobs"
BASELINE_TABLES = (
    "public.catalog_snapshots",
    "public.ecomm_api_product_edits",
    "public.kiki_evidence_documents",
    "public.kiki_evidence_dossiers",
    "public.kiki_editorial_batches",
)


def migrate_once(engine, *, expected_database=TARGET_DB):
    """Apply existing approved DDL in one transaction, or verify existing table.

    Only the startup token can call this in production. A single advisory
    transaction lock serializes competing instances. Existing rows are never
    modified; PostgreSQL automatically rolls back all DDL on any failure.
    """
    if engine.dialect.name != "postgresql":
        raise ValueError("KIKI intake: sólo PostgreSQL, ninguna migración ejecutada.")
    with engine.begin() as connection:
        connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        connection.execute(text("SET LOCAL search_path TO public"))
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(text("SET LOCAL statement_timeout = '30s'"))
        identity = connection.execute(
            text("SELECT current_database(), current_setting('server_version_num')::integer, current_setting('transaction_read_only')")
        ).one()
        if identity[0] != expected_database or identity[1] // 10000 != 18 or identity[2] != "off":
            raise ValueError("KIKI intake: nombre, versión de PostgreSQL o acceso de escritura no autorizado.")
        if not connection.execute(text("SELECT pg_try_advisory_xact_lock(24002027)")).scalar_one():
            raise ValueError("KIKI intake: existe otra migración activa. Sin cambios.")
        baseline = {}
        for qualified in BASELINE_TABLES:
            if connection.execute(
                text("SELECT to_regclass(:table_name)"), {"table_name": qualified}
            ).scalar_one() is None:
                raise ValueError("KIKI intake: faltan tablas originales; no se aplicó la migración.")
            baseline[qualified] = connection.execute(
                text("SELECT count(*) FROM " + qualified)
            ).scalar_one()
        existing = connection.execute(
            text("SELECT to_regclass(:name)"), {"name": EXPECTED_TABLE}
        ).scalar_one()
        created = existing is None
        if created:
            for statement in UP:
                connection.execute(text(statement))
        columns = set(connection.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='kiki_source_intake_jobs'"
        )).scalars())
        required = {col.name for col in SourceIntakeJob.__table__.columns}
        if columns != required:
            raise ValueError("KIKI intake: columnas de la cola no corresponden al esquema aprobado.")
        indexes = set(connection.execute(text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname='public' AND tablename='kiki_source_intake_jobs'"
        )).scalars())
        if not {"kiki_source_intake_jobs_pkey", "kiki_source_intake_jobs_request_key_key",
                "kiki_source_intake_created_idx"} <= indexes:
            raise ValueError("KIKI intake: índice/clave de coordinación incompletos.")
        for qualified, initial_count in baseline.items():
            if connection.execute(text("SELECT count(*) FROM " + qualified)).scalar_one() != initial_count:
                raise ValueError("KIKI intake: recuento original inesperado. Reversión automática.")
        return {"created": created, "table": EXPECTED_TABLE, "columns": len(required)}
