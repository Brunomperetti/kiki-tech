"""Contractual full-catalog audit from one complete Ecomm-App API capture.

This is not an autonomous researcher or a claim that a barcode proves product
identity. Outputs exact per-variant exceptions for research, copy, taxonomy,
media and monthly review, without provider, AI or database writes.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from io import StringIO
import csv

from sqlalchemy import select

from app.database.models import EcommApiProductEdit
from app.services.ecomm_api_work_queue_service import build_queue
from app.services.ecomm_api_product_workspace_service import (
    _readiness, blank_fields, review_schedule,
)
from app.services.documental.storage import Document, Dossier
from app.services.research_manifest_service import _cell

GAPS = (
    "IDENTITY_CONFLICT", "BARCODE_RESEARCH_NOT_ELIGIBLE",
    "NO_MANUFACTURER_DOCUMENT", "SOURCE_NOT_REVIEWED",
    "NO_CURRENT_APPROVED_FACTS", "INCOMPLETE_COMMERCIAL_FICHE",
    "TAXONOMY_MISSING", "SEO_MISSING", "IMAGE_MISSING",
    "VIDEO_NOT_DOCUMENTED", "MEDIA_RIGHTS_NOT_VERIFIED",
    "MONTHLY_REVIEW_DUE", "READY_WITHOUT_VERIFIED_DOCUMENTAL_GATE",
)
LABELS = {
    "IDENTITY_CONFLICT": "Verificar identidad SKU/variante",
    "BARCODE_RESEARCH_NOT_ELIGIBLE": "Revisar elegibilidad para investigar con código API",
    "NO_MANUFACTURER_DOCUMENT": "Conseguir original del fabricante o etiqueta",
    "SOURCE_NOT_REVIEWED": "Revisar identidad y procedencia del documento",
    "NO_CURRENT_APPROVED_FACTS": "Aprobar hechos con originales vigentes",
    "INCOMPLETE_COMMERCIAL_FICHE": "Completar la ficha comercial",
    "TAXONOMY_MISSING": "Completar categoría y subcategoría",
    "SEO_MISSING": "Completar los metadatos SEO",
    "IMAGE_MISSING": "Conseguir imagen con procedencia documentada",
    "VIDEO_NOT_DOCUMENTED": "Verificar disponibilidad de video del producto",
    "MEDIA_RIGHTS_NOT_VERIFIED": "Comprobar derechos de uso de multimedia",
    "MONTHLY_REVIEW_DUE": "Revisar la ficha y sus fuentes del último mes",
    "READY_WITHOUT_VERIFIED_DOCUMENTAL_GATE": "Revalidar respaldo documental antes de distribuir",
}
MAX_VARIANTS = 10000
ORDER = (
    "IDENTITY_CONFLICT", "NO_MANUFACTURER_DOCUMENT", "SOURCE_NOT_REVIEWED",
    "NO_CURRENT_APPROVED_FACTS", "MONTHLY_REVIEW_DUE",
    "INCOMPLETE_COMMERCIAL_FICHE", "TAXONOMY_MISSING",
    "SEO_MISSING", "IMAGE_MISSING", "MEDIA_RIGHTS_NOT_VERIFIED",
    "VIDEO_NOT_DOCUMENTED", "BARCODE_RESEARCH_NOT_ELIGIBLE",
    "READY_WITHOUT_VERIFIED_DOCUMENTAL_GATE",
)
CSV_HEADER = (
    "ecomm_id", "sku", "nombre_api", "presentacion_api",
    "barcode_api_solo_busqueda", "captura_api", "estado_editorial",
    "documentos", "fuentes_revisadas", "hechos_aprobados_con_original_vigente",
    "ficha_interna_completa", "imagen_en_ficha", "video_en_ficha",
    "revision_mensual_vencida", "siguiente_accion", "pendientes",
    "fuente_solo_por_api", "validacion_fabricante_requerida",
)


def _document_index(db):
    """Read only compact metadata; never download original HTML to audit."""
    docs = defaultdict(list)
    current = {}
    rows = db.execute(
        select(
            Document.id, Document.version, Document.digest,
            Document.body["associated_ecomm_id"].as_string(),
            Document.body["source"]["review_state"].as_string(),
            Document.body["origin_kind"].as_string(),
            Document.body["parse_status"].as_string(),
            Document.body["original"]["sha256"].as_string(),
            Document.body["synthetic"].as_boolean(),
        )
    )
    for doc_id, version, sha, ident, state, origin, parse_status, original_sha, synthetic in rows:
        if not ident:
            continue
        current[doc_id] = (version, sha, ident, state, bool(
            origin == "FILE" and parse_status == "TEXT_EXTRACTED"
            and isinstance(original_sha, str) and len(original_sha) == 64
            and synthetic is False
        ))
        docs[ident].append(doc_id)
    return docs, current


def _approved_index(db, current):
    counts = Counter()
    for ident, facts in db.execute(select(Dossier.ecomm_id, Dossier.facts)):
        for fact in facts or []:
            if not isinstance(fact, dict) or fact.get("state") != "APPROVED":
                continue
            doc = current.get(fact.get("document_id"))
            if doc is None or doc[2] != ident or doc[3] != "REVIEWED" or not doc[4]:
                continue
            if (
                doc[0] != fact.get("document_version")
                or doc[1] != fact.get("document_hash")
            ):
                continue
            counts[ident] += 1
    return counts


def _gap_report(row, edit, document_ids, documents, approved):
    fields = {**blank_fields(), **dict(edit.fields or {})} if edit else blank_fields()
    media = fields.get("media") or []
    image = any(m.get("kind") == "IMAGE" for m in media)
    video = any(m.get("kind") == "VIDEO" for m in media)
    primary = any(
        s.get("kind") in ("FABRICANTE", "ETIQUETA") and s.get("verified") is True
        for s in fields["sources"]
    )
    editorial_complete = bool(
        edit and edit.status == "READY_FOR_CHANNELS" and _readiness(fields)["ready"]
    )
    reviewed_sources = sum(
        documents[d][3] == "REVIEWED" and documents[d][4]
        for d in document_ids
    )
    due = review_schedule(edit)["review_due"] if edit else False
    gap = set()
    if row["identity_issue"] or (edit is not None and edit.source_sku != row["sku"]):
        gap.add("IDENTITY_CONFLICT")
    if "research_gtin_unique" not in row["flags"]:
        gap.add("BARCODE_RESEARCH_NOT_ELIGIBLE")
    if not document_ids:
        gap.add("NO_MANUFACTURER_DOCUMENT")
    elif reviewed_sources == 0:
        gap.add("SOURCE_NOT_REVIEWED")
    if approved == 0:
        gap.add("NO_CURRENT_APPROVED_FACTS")
    if not editorial_complete:
        gap.add("INCOMPLETE_COMMERCIAL_FICHE")
    if not fields["category"] or not fields["subcategory"]:
        gap.add("TAXONOMY_MISSING")
    if not all(fields[key] for key in ("seo_title", "seo_description", "seo_keywords")):
        gap.add("SEO_MISSING")
    if not image:
        gap.add("IMAGE_MISSING")
    if not video:
        # Track as a coverage requirement, not necessarily mandatory:
        # some manufacturers have no video available or licensed.
        gap.add("VIDEO_NOT_DOCUMENTED")
    if media:
        # A media URL alone does not prove licensed commercial use.
        # This audit does not inspect original grant bytes or claim rights.
        gap.add("MEDIA_RIGHTS_NOT_VERIFIED")
    if due:
        gap.add("MONTHLY_REVIEW_DUE")
    if editorial_complete and (not primary or reviewed_sources == 0 or approved == 0):
        gap.add("READY_WITHOUT_VERIFIED_DOCUMENTAL_GATE")
    ordered = [key for key in ORDER if key in gap]
    return {
        "ecomm_id": row["ecomm_id"],
        "sku": row["sku"],
        "name": row["product_name"],
        "presentation": row["source"].get("variant_description") or "",
        "api_barcode": row["source"].get("barcode") or "",
        "captured_at": row.get("captured_at"),
        "editorial_status": edit.status if edit else "NOT_STARTED",
        "documents": len(document_ids),
        "reviewed_source_documents": reviewed_sources,
        "approved_facts_with_current_original": approved,
        "internal_fiche_complete": editorial_complete,
        "image_present": image,
        "video_present": video,
        "monthly_review_due": due,
        "next_step": ordered[0] if ordered else "REVIEW_FOR_DELIVERY",
        "gaps": ordered,
        # Deliberate: a structural audit is NOT sufficient to certify claims,
        # identity of the manufacturer, media rights or final publication.
        "delivery_certified": False,
        "source": "ECOMM_APP_API_STAGE",
    }


def summarize_rows(rows):
    totals = Counter()
    detail = Counter()
    for row in rows:
        totals[row["editorial_status"]] += 1
        detail.update(row["gaps"])
    return {
        "mode": "READ_ONLY_CONTRACTUAL_CATALOG_AUDIT",
        "source": "ECOMM_APP_API_STAGE",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(rows),
        "editorial_status": dict(sorted(totals.items())),
        "gap_counts": {key: detail[key] for key in GAPS},
        "next_actions": dict(Counter(row["next_step"] for row in rows)),
        "internal_fiches_complete": sum(row["internal_fiche_complete"] for row in rows),
        "approved_claims_in_current_originals": sum(
            row["approved_facts_with_current_original"] for row in rows
        ),
        "external_writes_enabled": False,
        "network_requests": 0,
        "ai_requests": 0,
        "monthly_review_confirmed": False,
        "no_manual_data_entry": True,
        "policy": (
            "Auditoría operativa sobre captura API guardada; no es tiempo real "
            "ni certifica fuentes, derechos, identidad, calidad expresiva o "
            "publicación. Las propuestas requieren evidencias y aprobación."
        ),
    }


def build_delivery_audit(db):
    work = build_queue(db, export_rows=True)
    rows = work["items"]
    if len(rows) > MAX_VARIANTS or len({r["ecomm_id"] for r in rows}) != len(rows):
        raise ValueError("Captura duplicada o superior al límite de auditoría.")
    edit_map = {
        edit.ecomm_id: edit
        for edit in db.scalars(select(EcommApiProductEdit))
    }
    docs, current = _document_index(db)
    facts = _approved_index(db, current)
    report = [
        _gap_report(row, edit_map.get(row["ecomm_id"]),
                    docs.get(row["ecomm_id"], []), current,
                    facts[row["ecomm_id"]])
        for row in rows
    ]
    return summarize_rows(report), report


def export_delivery_csv(rows):
    if len(rows) > MAX_VARIANTS:
        raise ValueError("Exportación demasiado grande para una única consulta.")
    out = StringIO(newline="")
    csv_writer = csv.writer(out)
    csv_writer.writerow(CSV_HEADER)
    for r in sorted(rows, key=lambda row: (row["next_step"], row["sku"].casefold(), row["ecomm_id"])):
        values = (
            r["ecomm_id"], r["sku"], r["name"], r["presentation"],
            r["api_barcode"], r["captured_at"], r["editorial_status"],
            r["documents"], r["reviewed_source_documents"],
            r["approved_facts_with_current_original"],
            "SI" if r["internal_fiche_complete"] else "NO",
            "SI" if r["image_present"] else "NO",
            "SI" if r["video_present"] else "NO",
            "SI" if r["monthly_review_due"] else "NO",
            r["next_step"], " | ".join(r["gaps"]),
            "SI", "SI",
        )
        csv_writer.writerow([_cell(str(v) if isinstance(v, int) else v) for v in values])
    return "\ufeff" + out.getvalue()
