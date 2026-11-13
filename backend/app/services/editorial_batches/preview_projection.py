"""Read projections for analysis only: originals and decision histories stay in PG."""

from types import SimpleNamespace
from sqlalchemy import select, cast, func, literal, text, bindparam, String
from sqlalchemy.dialects.postgresql import JSONB, JSONPATH, ARRAY
from app.database.models import EcommApiProductEdit


def project(db, ids, budget):
    fields_size = db.scalar(
        select(
            func.coalesce(
                func.sum(func.octet_length(cast(EcommApiProductEdit.fields, String))), 0
            )
        ).where(EcommApiProductEdit.ecomm_id.in_(ids))
    )
    if fields_size > budget:
        raise ValueError("Campos editoriales exceden el presupuesto de análisis.")
    dates = func.jsonb_path_query_array(
        cast(EcommApiProductEdit.history, JSONB),
        cast(literal('$[*] ? (@.new_status == "READY_FOR_CHANNELS").at'), JSONPATH),
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
            dates.label("dates"),
        ).where(EcommApiProductEdit.ecomm_id.in_(ids))
    )
    edits = {
        r.ecomm_id: SimpleNamespace(
            **{k: v for k, v in r._mapping.items() if k != "dates"},
            history=[{"new_status": "READY_FOR_CHANNELS", "at": at} for at in r.dates],
        )
        for r in rows
    }
    query = text("""SELECT ecomm_id, version, identity, identity_digest,
      COALESCE((SELECT jsonb_agg(f - 'history') FROM jsonb_array_elements(facts::jsonb) f), '[]'::jsonb) AS facts
      FROM kiki_evidence_dossiers WHERE ecomm_id=ANY(:ids)""").bindparams(
        bindparam("ids", type_=ARRAY(String))
    )
    import json

    dossiers = {}
    size = fields_size
    for row in db.execute(query, {"ids": ids}).mappings():
        size += len(json.dumps(row["facts"], ensure_ascii=False).encode())
        if size > budget:
            raise ValueError("Hechos documentales exceden el presupuesto de análisis.")
        dossiers[row["ecomm_id"]] = SimpleNamespace(**row)
    return edits, dossiers
