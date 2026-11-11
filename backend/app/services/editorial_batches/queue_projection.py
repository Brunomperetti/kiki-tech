"""Small read projections. Never store presence markers as commercial content."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from sqlalchemy import select, cast, func, case, literal
from sqlalchemy.dialects.postgresql import JSONB, JSONPATH
from app.database.models import EcommApiProductEdit
from app.services.documental.storage import Document
from app.services.ecomm_api_product_workspace_service import (
    TEXT_LIMITS,
    review_schedule,
)


def queue_edits(db):
    if db.bind.dialect.name != "postgresql":
        return {x.ecomm_id: x for x in db.scalars(select(EcommApiProductEdit))}
    fields = cast(EcommApiProductEdit.fields, JSONB)
    parts = []
    for key in TEXT_LIMITS:
        value = fields[key].astext
        if key not in {
            "brand",
            "manufacturer",
            "title",
            "presentation",
            "proposed_gtin",
        }:
            value = case(
                (func.length(func.btrim(value)) > 0, literal("present")),
                else_=literal(""),
            )
        parts.extend([key, value])

    def path(expression, value):
        return func.jsonb_path_query_array(expression, cast(literal(value), JSONPATH))

    parts.extend(
        [
            "attributes",
            path(fields, "$.attributes[*].name"),
            "media",
            path(fields, "$.media[*].kind"),
            "sources",
            path(fields, "$.sources[*] ? (@.verified == true).kind"),
        ]
    )
    history = path(
        cast(EcommApiProductEdit.history, JSONB),
        '$[*] ? (@.new_status == "READY_FOR_CHANNELS").at',
    )
    rows = db.execute(
        select(
            EcommApiProductEdit.ecomm_id,
            EcommApiProductEdit.source_sku,
            EcommApiProductEdit.version,
            EcommApiProductEdit.status,
            EcommApiProductEdit.updated_at,
            func.jsonb_build_object(*parts).label("fields"),
            history.label("review_dates"),
        )
    )
    result = {}
    for row in rows:
        values = dict(row._mapping)
        values["fields"]["media"] = [{"kind": k} for k in values["fields"]["media"]]
        values["fields"]["sources"] = [
            {"kind": k, "verified": True} for k in values["fields"]["sources"]
        ]
        values["history"] = [
            {"new_status": "READY_FOR_CHANNELS", "at": at}
            for at in values.pop("review_dates")
        ]
        result[row.ecomm_id] = SimpleNamespace(**values)
    return result


def editorial_flags(db, edits, soon_days):
    # No original bytes, quotes, sections or histories needed for queue triage.
    # Histories can grow; strip each using SQL subquery before transfer.
    from sqlalchemy import text

    rows = db.execute(
        text(
            "SELECT ecomm_id, COALESCE((SELECT jsonb_agg(jsonb_build_object('state', f->>'state', 'document_id', f->>'document_id', 'document_version', f->'document_version', 'document_hash',f->>'document_hash')) FROM jsonb_array_elements(facts::jsonb) f), '[]'::jsonb) AS facts FROM kiki_evidence_dossiers"
        )
    )
    documents = {
        r.id: r
        for r in db.execute(select(Document.id, Document.version, Document.digest))
    }
    result = {}
    for row in rows:
        flags = []
        if any(f["state"] == "APPROVED" for f in row.facts):
            flags.append("evidence_approved")
        if any(f["state"] == "REVOKED" for f in row.facts):
            flags.append("evidence_revoked")
        if any(
            f["document_id"] not in documents
            or (documents[f["document_id"]].version, documents[f["document_id"]].digest)
            != (f["document_version"], f["document_hash"])
            for f in row.facts
        ):
            flags.append("documents_changed")
        result[row.ecomm_id] = flags
    for ident, edit in edits.items():
        schedule = review_schedule(edit)
        due = schedule["next_review_at"]
        if (
            due
            and not schedule["review_due"]
            and datetime.fromisoformat(due)
            <= datetime.now(timezone.utc) + timedelta(days=soon_days)
        ):
            result.setdefault(ident, []).append("review_soon")
    return result
