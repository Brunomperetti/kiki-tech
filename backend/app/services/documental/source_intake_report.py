"""Bounded, read-only stage-3 coverage and cited deterministic planning.

The existing queue owns execution, Research owns decisions and Proposals owns
generation. This projection neither creates dossiers nor approves/saves fields.
"""

from collections import Counter
from copy import deepcopy
import csv
import hmac
from io import StringIO
from types import SimpleNamespace

from app.core.config import get_settings
from app.services.commercial_channel_export_service import _cell
from app.services.editorial_batches.context import Context, sources
from .commercial_plan import summarize_inspections
from .research import identity_digest
from .source_intake_queue import MAX_ITEMS, SourceIntakeQueue
from .source_intake_pipeline import check_identity
from .storage import digest
from .taxonomy_alignment import reviewed_internal_pairs
from .taxonomy_review import current_review, histories_for

SCHEMA = "kiki-documental-pipeline-v1"
STATES = ("READY", "RESEARCH", "REVIEW_REQUIRED", "BLOCKED", "FAILED")


def _claims(context, db, ident, session):
    dossier = context.dossiers.get(ident)
    if not dossier:
        return [], []
    research = context.Research(db, session)
    reference = research.reference(ident)
    case = SimpleNamespace(
        ecomm_id=ident,
        identity=reference,
        identity_digest=identity_digest(reference),
        facts=deepcopy(dossier.facts),
        history=deepcopy(dossier.history),
    )
    claims, approved = [], []
    for fact in case.facts:
        if fact.get("ecomm_id") != ident:
            continue
        blockers = research.blockers(case, fact)
        doc = context.documents.get(fact.get("document_id"))
        citation = {
            "fact_id": fact["id"],
            "document_id": fact.get("document_id"),
            "document_version": fact.get("document_version"),
            "document_hash": fact.get("document_hash"),
            "document_sha256": (doc.body.get("original") or {}).get("sha256")
            if doc
            else None,
            "url": (doc.body.get("source") or {}).get("reference_url") if doc else None,
            "quote": fact.get("quote"),
            "location": fact.get("location"),
        }
        claims.append(
            {
                "id": fact["id"],
                "field": fact["field"],
                "value": fact["value"],
                "unit": fact.get("unit"),
                "state": fact["state"],
                "version": fact["version"],
                "verified": fact["state"] == "APPROVED" and not blockers,
                **citation,
                "blockers": blockers,
            }
        )
        if fact["state"] == "APPROVED" and not blockers:
            approved.append(fact)
    return claims, approved


def _state(row, inspected, fields, has_document):
    processing = row.get("processing") or {}
    if row["state"] == "CANCELLED":
        return "BLOCKED"
    if processing.get("phase") == "FAILED":
        return "FAILED"
    if (
        processing.get("phase") == "BLOCKED"
        or row["state"] == "BLOCKED"
        or inspected.get("conflicts")
        or inspected.get("stale")
    ):
        return "BLOCKED"
    if not has_document:
        return "RESEARCH"
    if fields:
        return "READY"
    return "REVIEW_REQUIRED"


def build_intake_report(
    db, session, job_id, *, context_type=Context, source_loader=sources
):
    queue = SourceIntakeQueue(db, session, "")
    # Same lock order as execution and documentary review. A report cannot
    # combine yesterday's job revision with facts committed while it waited.
    # Routes roll back this read-only transaction before returning.
    job = queue._get(job_id, locked=True)
    if not 1 <= len(job.items) <= MAX_ITEMS:
        raise ValueError("Lote fuera del límite de 20 variantes.")
    ids = [row["ecomm_id"] for row in job.items]
    if len(set(ids)) != len(ids):
        raise ValueError("El lote contiene identidades repetidas.")
    catalog = source_loader(db)
    present = [ident for ident in ids if ident in catalog]
    context = context_type(
        db, present, catalog, get_settings().kiki_editorial_context_bytes
    )
    rows = []
    try:
        histories = histories_for(
            db, present, byte_limit=get_settings().kiki_editorial_context_bytes
        )
        vocabulary = reviewed_internal_pairs(db)
        for entry in job.items:
            ident = entry["ecomm_id"]
            source = catalog.get(ident) or {}
            inspected, fields, claims, reasons = {}, {}, [], []
            plan = {"fields": {}, "blocked_reasons": []}
            try:
                if not source:
                    raise ValueError(
                        "La variante ya no está en la captura completa API; revisar identidad."
                    )
                check_identity(entry, catalog)
                inspected = context.inspect(db, session, ident)
                inspected["ecomm_id"] = ident
                inspected["reviewed_taxonomy_mapping"] = current_review(
                    inspected, histories.get(ident, []), "KIKI"
                )
                claims, approved = _claims(context, db, ident, session)
                summary = summarize_inspections([(ident, inspected)], vocabulary)[
                    "items"
                ][0]
                proposed, missing = context.Proposals.generate_fields(approved)
                if inspected["eligible"] and not inspected["stale"]:
                    citations = {fact["id"]: fact for fact in claims}
                    fields = {
                        key: {
                            **value,
                            "citations": [citations[i] for i in value["evidence_ids"]],
                        }
                        for key, value in proposed.items()
                        if key in summary["fields_supported"]
                    }
                reasons = list(
                    dict.fromkeys(
                        [
                            *summary["reasons"],
                            *missing,
                            *(
                                f"{field}: sin respaldo vigente o requiere revisión; no se propone."
                                for field in summary["fields_needing_support"]
                            ),
                        ]
                    )
                )
                plan = {
                    "fields": fields,
                    "blocked_reasons": reasons,
                    "next_task": summary["next_task"],
                    "next_task_label": summary["next_task_label"],
                    "versions": inspected["expected"],
                }
            except ValueError as exc:
                inspected = {"conflicts": True}
                reasons = [str(exc)]
                plan["blocked_reasons"] = reasons
            doc = context.documents.get(entry.get("document_id"))
            if doc and doc.body.get("associated_ecomm_id") != ident:
                doc = None
                inspected = {"conflicts": True}
                reasons.append("El original no pertenece al Ecomm ID exacto.")
                plan = {"fields": {}, "blocked_reasons": reasons}
                fields = {}
            processing = entry.get("processing") or {}
            if (
                doc
                and processing.get("document_sha256")
                and (
                    (doc.body.get("original") or {}).get("sha256")
                    != processing["document_sha256"]
                    or processing.get("document_id") != doc.id
                )
            ):
                inspected = {"conflicts": True}
                reasons.append(
                    "Cambió el original fijado en el lote; se requiere revisión nueva."
                )
                plan = {"fields": {}, "blocked_reasons": reasons}
                fields = {}
            rows.append(
                {
                    "ecomm_id": ident,
                    "sku": source.get("sku"),
                    "barcode": source.get("barcode"),
                    "gtin": source.get("gtin"),
                    "name": source.get("product_name"),
                    "presentation": source.get("variant_description"),
                    "is_combo": source.get("is_combo"),
                    "url": entry.get("url"),
                    "legacy_state": entry["state"],
                    "state": _state(entry, inspected, fields, bool(doc)),
                    "attempts": entry.get("attempts", 0),
                    "document_id": doc.id if doc else None,
                    "document_version": doc.version if doc else None,
                    "document_digest": doc.digest if doc else None,
                    "complete_available": bool(doc)
                    and entry.get("identity_schema") == 2
                    and entry["state"] != "RUNNING"
                    and job.state != "CANCELLED"
                    and (
                        processing.get("phase") != "EXTRACTED"
                        or processing.get("document_version") != doc.version
                        or processing.get("document_digest") != doc.digest
                    ),
                    "document_sha256": (doc.body.get("original") or {}).get("sha256")
                    if doc
                    else None,
                    "source_state": (doc.body.get("source") or {}).get("review_state")
                    if doc
                    else None,
                    "processing": processing,
                    "processing_status": processing.get("phase", "PENDING"),
                    "claims": claims,
                    "plan": plan,
                    "blockers": list(
                        dict.fromkeys(
                            [
                                *inspected.get("reasons", []),
                                *([entry["error"]] if entry.get("error") else []),
                                *(
                                    ["Variante ausente de la captura API."]
                                    if not source
                                    else []
                                ),
                            ]
                        )
                    ),
                    "human_review_required": True,
                }
            )
    finally:
        context.release()
    counts = Counter(row["state"] for row in rows)
    result = {
        "mode": "SOURCE_INTAKE_PIPELINE_REPORT",
        "schema_version": SCHEMA,
        "job_id": job.id,
        "revision": job.revision,
        "total": len(rows),
        "summary": {state: counts[state] for state in STATES},
        "items": rows,
        "metrics": {
            "processed": sum(
                bool(row["attempts"] or row["document_id"]) for row in rows
            ),
            "classified": len(rows),
            "pending_facts": sum(
                f["state"] == "PENDING" for row in rows for f in row["claims"]
            ),
            "without_source": sum(not row["document_id"] for row in rows),
            "failed": counts["FAILED"],
            "attempts_total": sum(row["attempts"] for row in rows),
            "documents_recorded": sum(bool(row["document_id"]) for row in rows),
            "source_bytes_recorded": sum(
                (row["processing"] or {}).get("source_bytes") or 0 for row in rows
            ),
            "duration_ms": sum(
                (row["processing"] or {}).get("elapsed_ms") or 0 for row in rows
            ),
            "ai_requests": 0,
            "ai_cost_usd": 0,
            "publication_writes": 0,
            "claims_approved_by_operation": 0,
            "commercial_fields_saved": 0,
        },
        "execution": "CLIENT_DRIVEN_ONE_ITEM_STEPS_NO_BACKGROUND_WORKER",
        "quota": {
            "max_variants": MAX_ITEMS,
            "max_attempts_per_item": 3,
            "source_daily_limit": "EXISTING_IMPORTER_LIMIT_UNCHANGED",
            "ai": "DISCONNECTED",
        },
        "history": deepcopy(job.history),
        "external_writes_enabled": False,
        "human_review_required": True,
    }
    result["fingerprint"] = digest(result)
    return result


def export_intake_exceptions(report, expected_revision, expected_fingerprint):
    if report["revision"] != expected_revision or not hmac.compare_digest(
        report["fingerprint"], expected_fingerprint
    ):
        raise ValueError(
            "Cambió el lote o sus evidencias; actualizá el resumen antes de exportar."
        )
    stream = StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(
        [
            "lote",
            "ecomm_id",
            "sku",
            "barcode_api",
            "estado",
            "url",
            "sha256_original",
            "motivo",
            "campos_pendientes",
        ]
    )
    for row in report["items"]:
        if row["state"] == "READY" and not row["plan"]["blocked_reasons"]:
            continue
        writer.writerow(
            [
                _cell(value)
                for value in (
                    report["job_id"],
                    row["ecomm_id"],
                    row["sku"],
                    row["barcode"],
                    row["state"],
                    row["url"],
                    row["document_sha256"],
                    " | ".join(row["blockers"]),
                    " | ".join(row["plan"]["blocked_reasons"]),
                )
            ]
        )
    result = stream.getvalue().encode("utf-8-sig")
    if len(result) > 10 * 1024 * 1024:
        raise ValueError(
            "Exportación demasiado grande; revisá el lote individualmente."
        )
    return result
