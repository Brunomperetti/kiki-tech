"""Explicit, bounded re-extraction of already reviewed local originals.

This is NOT automated product enrichment approval. It only puts document
claims into PENDING review. One source document per variant; ambiguous cases
remain blocked. No provider, AI, channel or media-rights calls.
"""
from collections import Counter

from sqlalchemy import select

from app.integrations.ecomm_app.api_catalog_browser import valid_variant_id
from app.services.documental.research import Research
from app.services.documental.storage import Document
from app.services.editorial_batches.context import sources


MAX_SELECTED = 20
MAX_REASONS = 4


def extract_reviewed_selection(db, session, ids):
    if (
        not isinstance(ids, list)
        or not 1 <= len(ids) <= MAX_SELECTED
        or len(set(ids)) != len(ids)
        or not all(isinstance(x, str) and valid_variant_id(x) for x in ids)
    ):
        raise ValueError("Seleccioná entre 1 y 20 Ecomm ID únicos y válidos.")
    # Fail closed on incomplete/stale API capture rather than switching to
    # historical Excel or a guessed product from a manufacturer name.
    catalog = sources(db)
    if any(ident not in catalog for ident in ids):
        raise ValueError("Una variante no está en la captura completa de Ecomm-App API.")
    results = []
    for ident in ids:
        entry = {
            "ecomm_id": ident,
            "state": "BLOCKED",
            "document_id": None,
            "document_version": None,
            "facts_pending": 0,
            "facts_approved_unchanged": 0,
            "reasons": [],
        }
        try:
            # No source fetch or external request; only previously archived
            # originals attached to this Ecomm ID may be considered.
            documents = db.scalars(
                select(Document).where(
                    Document.body["associated_ecomm_id"].as_string() == ident
                ).order_by(Document.id)
            ).all()
            valid = [
                doc for doc in documents
                if doc.body.get("source", {}).get("review_state") == "REVIEWED"
                and doc.body.get("synthetic") is False
                and doc.body.get("parse_status") == "TEXT_EXTRACTED"
            ]
            if len(valid) != 1:
                raise ValueError(
                    "Se requiere exactamente un original real revisado. "
                    "Si hay varios, elegí y contrastá la fuente desde Evidencias."
                )
            doc = valid[0]
            entry["document_id"] = doc.id
            entry["document_version"] = doc.version
            if not doc.body.get("claims"):
                raise ValueError(
                    "El documento revisado no contiene afirmaciones extraíbles."
                )
            service = Research(db, session)
            dossier = service.dossier(ident)
            blockers = [
                *service.identity_blockers(dossier, doc),
                *service.additional_blockers(dossier, doc),
                *(doc.body.get("parser_blockers") or []),
            ]
            if blockers:
                entry["reasons"] = list(dict.fromkeys(blockers))[:MAX_REASONS]
                raise ValueError(
                    "Resolvé los bloqueos de identidad y procedencia en Evidencias."
                )
            if doc.body.get("source", {}).get("review_state") != "REVIEWED":
                raise ValueError("La procedencia fue modificada por otra sesión.")
            # Research.extract enforces document version, exact Ecomm identity,
            # the current dossier version and fact provenance. Unchanged
            # already-approved claims are NOT downgraded.
            report = service.extract(ident, dossier.version, doc.id, doc.version)
            relevant = [
                f for f in report["facts"] if f["document_id"] == doc.id
            ]
            entry["facts_pending"] = sum(
                f["state"] == "PENDING" for f in relevant
            )
            entry["facts_approved_unchanged"] = sum(
                f["state"] == "APPROVED" and f["verified"] for f in relevant
            )
            entry["state"] = "PREPARED" if entry["facts_pending"] else "NO_CHANGES"
        except ValueError as exc:
            # Roll back any noncommitted invalidation for this one variant.
            db.rollback()
            entry["reasons"] = list(dict.fromkeys([
                *entry["reasons"], str(exc),
            ]))[:MAX_REASONS]
        except Exception:
            db.rollback()
            raise  # A systemic DB failure must not masquerade as a valid item.
        results.append(entry)
    counts = Counter(item["state"] for item in results)
    return {
        "mode": "MANUAL_REEXTRACT_REVIEWED_ORIGINALS",
        "total": len(results),
        "counts": {
            key: counts[key]
            for key in ("PREPARED", "NO_CHANGES", "BLOCKED")
        },
        "items": results,
        "human_fact_approval_required": True,
        "facts_approved_by_operation": 0,
        "external_writes_enabled": False,
        "provider_calls": 0,
        "ai_requests": 0,
        "product_fields_saved": 0,
        "automatic_publications": 0,
        "policy": (
            "Solo se reextraen hechos PENDIENTES de originales reales "
            "con procedencia e identidad ya revisadas. KIKI nunca aprueba "
            "hechos ni publica fichas al ejecutar este lote."
        ),
    }
