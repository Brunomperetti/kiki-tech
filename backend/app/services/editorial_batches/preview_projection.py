"""Bounded preview projections retain identity reviews, not originals/fact histories."""

from types import SimpleNamespace
from sqlalchemy import select, cast, func, literal, text, bindparam, String
from sqlalchemy.dialects.postgresql import JSONB, JSONPATH, ARRAY
from app.database.models import EcommApiProductEdit


def _edit_projection(row):
    # Keep the actual review actions, previous status and change set. Rebuilding
    # an event from its date makes every save look like an initial sign-off.
    return SimpleNamespace(
        **{k: v for k, v in row._mapping.items() if k != "review_events"},
        history=row.review_events,
    )


def project(db, ids, budget):
    review_events = func.jsonb_path_query_array(
        cast(EcommApiProductEdit.history, JSONB),
        cast(literal('$[*] ? (@.new_status == "READY_FOR_CHANNELS")'), JSONPATH),
    )
    fields_size = db.scalar(
        select(
            func.coalesce(
                func.sum(
                    func.octet_length(cast(EcommApiProductEdit.fields, String))
                    + func.octet_length(cast(review_events, String))
                ),
                0,
            )
        ).where(EcommApiProductEdit.ecomm_id.in_(ids))
    )
    if fields_size > budget:
        raise ValueError(
            "Campos o revisiones editoriales exceden el presupuesto de análisis."
        )
    rows = db.execute(
        select(
            EcommApiProductEdit.ecomm_id,
            EcommApiProductEdit.source_sku,
            EcommApiProductEdit.fields,
            EcommApiProductEdit.status,
            EcommApiProductEdit.version,
            EcommApiProductEdit.created_at,
            EcommApiProductEdit.updated_at,
            review_events.label("review_events"),
        ).where(EcommApiProductEdit.ecomm_id.in_(ids))
    )
    edits = {r.ecomm_id: _edit_projection(r) for r in rows}
    projection = """SELECT ecomm_id, version, identity, identity_digest,
      COALESCE((SELECT jsonb_agg(f - 'history') FROM jsonb_array_elements(facts::jsonb) f), '[]'::jsonb) AS facts,
      jsonb_path_query_array(history::jsonb,
        '$[*] ? (@.action == "DOCUMENT_IDENTITY_REVIEW")') AS history
      FROM kiki_evidence_dossiers WHERE ecomm_id=ANY(:ids)"""
    binding = bindparam("ids", type_=ARRAY(String))
    projected_size = db.scalar(
        text(
            "SELECT COALESCE(SUM(octet_length(facts::text) + "
            "octet_length(history::text) + octet_length(identity::text)), 0) "
            "FROM (" + projection + ") AS bounded_dossiers"
        ).bindparams(binding),
        {"ids": ids},
    )
    if fields_size + projected_size > budget:
        raise ValueError(
            "Hechos o decisiones documentales exceden el presupuesto de análisis."
        )
    query = text(projection).bindparams(binding)
    import json

    dossiers = {}
    size = fields_size
    for row in db.execute(query, {"ids": ids}).mappings():
        size += sum(
            len(json.dumps(row[key], ensure_ascii=False).encode())
            for key in ("facts", "identity", "history")
        )
        if size > budget:
            raise ValueError("Hechos documentales exceden el presupuesto de análisis.")
        dossiers[row["ecomm_id"]] = SimpleNamespace(**row)
    return edits, dossiers
