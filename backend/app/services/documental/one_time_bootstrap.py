"""Explicit opt-in, atomic, additive PostgreSQL 18 schema installation.

Run ONLY in the existing KIKI backend at startup after a backup has been
validated and the expected DB name has been independently confirmed.
Never mutates source/catalog/edit/ML/TN tables. No automatic invocation
without a one-time deployment environment switch. All statements already
pass the disposable PostgreSQL 18 migration CI.
"""
import logging

from sqlalchemy import text

from app.services.v2_schema import statements

log = logging.getLogger(__name__)

REQUIRED_CORE = ("catalog_snapshots", "ecomm_api_product_edits")
SCHEMA_TABLES = (
    "kiki_evidence_control",
    "kiki_evidence_documents",
    "kiki_evidence_dossiers",
    "kiki_editorial_batches",
    "kiki_editorial_batch_items",
    "kiki_editorial_batch_signals",
)


def apply_additive_schema(engine, *, expected_database):
    """One transaction, advisory lock, short timeouts, fail-closed verification.

    The caller is responsible for opt-in, restoring a backup if necessary,
    and confirming the target DB. No credentials or SQL user input logged.
    """
    if not expected_database or expected_database != "kiki_tech_db":
        raise ValueError("Esquema KIKI: nombre de base objetivo no autorizado.")
    with engine.begin() as connection:
        database = connection.execute(text("SELECT current_database()")).scalar_one()
        if database != expected_database:
            raise ValueError("Esquema KIKI: base diferente del objetivo autorizado.")
        connection.execute(text("SET LOCAL search_path TO public"))
        connection.execute(text("SET LOCAL lock_timeout = '3s'"))
        connection.execute(text("SET LOCAL statement_timeout = '15s'"))
        locked = connection.execute(
            text("SELECT pg_try_advisory_xact_lock(24002026)")
        ).scalar_one()
        if locked is not True:
            raise ValueError("Esquema KIKI: otra migración tiene el bloqueo activo.")

        for name in REQUIRED_CORE:
            found = connection.execute(
                text("SELECT to_regclass(:name) IS NOT NULL"),
                {"name": "public." + name},
            ).scalar_one()
            if not found:
                raise ValueError(
                    "Esquema KIKI: faltan tablas originales. Migración cancelada."
                )
        # BEGIN transaction is controlled by SQLAlchemy. Each DO fails
        # on a partially installed family; PostgreSQL rolls everything back.
        for statement in statements():
            connection.execute(text(statement))
        for name in SCHEMA_TABLES:
            found = connection.execute(
                text("SELECT to_regclass(:name) IS NOT NULL"),
                {"name": "public." + name},
            ).scalar_one()
            if not found:
                raise ValueError(
                    "Esquema KIKI: no se instaló el grupo documental completo."
                )
        control = connection.execute(
            text("SELECT id FROM kiki_evidence_control")
        ).scalars().all()
        if control != [1]:
            raise ValueError(
                "Esquema KIKI: control de concurrencia incompleto."
            )
        indexes = connection.execute(text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname='public' AND tablename='kiki_evidence_documents'"
        )).scalars().all()
        if "kiki_evidence_documents_variant" not in indexes:
            raise ValueError(
                "Esquema KIKI: índice documental obligatorio ausente."
            )
    log.warning(
        "KIKI_BOOTSTRAP_ADDRESSED: schema verified atomically, target=%s, "
        "core tables unchanged, catalog/provider writes=0",
        expected_database,
    )
    return {"schema_verified": True, "tables": len(SCHEMA_TABLES)}
