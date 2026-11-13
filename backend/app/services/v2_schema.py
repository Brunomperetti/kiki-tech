"""Print the EXISTING additive migrations. No settings, engine or DB connection.

Review stdout before any separately authorized application with psql. No core
tables are altered; a partially installed group is rejected for manual review.
"""
from .documental.migration import UP as DOCUMENT_UP
from .editorial_batches.migration import UP as BATCH_UP
from .editorial_batches.migration_2r import UP as EXECUTOR_UP


def statements():
    groups = (
        (("kiki_evidence_control", "kiki_evidence_documents", "kiki_evidence_dossiers"), DOCUMENT_UP),
        (("kiki_editorial_batches", "kiki_editorial_batch_items"), BATCH_UP),
        (("kiki_editorial_batch_signals",), EXECUTOR_UP),
    )
    for tables, operations in groups:
        present = [f"to_regclass('public.{name}') IS NOT NULL" for name in tables]
        yield "DO $kiki_v2$ BEGIN\n" + (
            "IF (" + " OR ".join(present) + ") AND NOT (" + " AND ".join(present) + ") THEN\n"
            "RAISE EXCEPTION 'Esquema parcial: revisar antes de continuar';\n"
            "ELSIF NOT (" + present[0] + ") THEN\n"
            + ";\n".join(operations) + ";\nEND IF;\nEND $kiki_v2$;"
        )


def sql():
    return "\n".join((
        "-- SOLO PREPARACIÓN. Aplicar requiere autorización y copia validada.",
        "\\set ON_ERROR_STOP on",
        "BEGIN;",
        "SET LOCAL search_path TO public;",
        "SET LOCAL lock_timeout = '5s';",
        "SELECT pg_advisory_xact_lock(24002026);",
        *statements(),
        "COMMIT;",
    ))


if __name__ == "__main__":
    print(sql())
