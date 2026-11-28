"""Read-only, reviewed commercial packages; never native provider import files.

One preview is bound to source identity, all 18 saved fields, documentary
versions, rights decisions and monthly-review state. Export recomputes it;
neither request approves, reconciles, saves, publishes nor calls a provider.
"""

import csv
from copy import deepcopy
from datetime import datetime, timezone
import hmac
import importlib
from io import StringIO
import json
from types import SimpleNamespace

from sqlalchemy import cast, func, select, Text
from sqlalchemy.orm import load_only

from app.database.models import EcommApiProductEdit, KikiAiEditorialDraft
from app.integrations.ecomm_app.api_catalog_browser import valid_variant_id
from app.services.contractual_delivery_audit_service import (
    build_delivery_audit,
    export_delivery_csv,
)
from app.services.documental.channel_readiness_guard import require_primary_evidence
from app.services.documental.research import Research, identity_digest, fact_digest
from app.services.documental.storage import Control, Document, Dossier, digest
from app.services.ecomm_api_product_workspace_service import (
    blank_fields,
    review_schedule,
    _readiness,
    _gtin_check_digit_valid,
)
from app.services.editorial_batches.context import sources

MAX_ITEMS = 20
MAX_BYTES = 10 * 1024 * 1024
CONTEXT_BYTES = 32 * 1024 * 1024
CONTENT_FIELDS = (
    "brand",
    "manufacturer",
    "title",
    "short_title",
    "short_description",
    "description",
    "details",
    "presentation",
    "category",
    "subcategory",
    "seo_title",
    "seo_description",
    "seo_keywords",
    "proposed_gtin",
    "attributes",
    "media",
)


def _cell(value):
    text = "" if value is None else str(value)
    if len(text) > 128 * 1024:
        raise ValueError(
            "Una celda supera el límite; no se exportó contenido truncado."
        )
    if text.lstrip(" \t\r\n\v\f\ufeff").startswith(
        ("=", "+", "-", "@")
    ) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def _check_fingerprint(expected, actual):
    if (
        not isinstance(expected, str)
        or len(expected) != 64
        or not hmac.compare_digest(expected, actual)
    ):
        raise ValueError(
            "La previsualización cambió o falta. Revisá nuevamente antes de exportar."
        )


class ReadOnlyResearch(Research):
    """Reuse evidence rules while forbidding Research.dossier's write path."""

    def __init__(self, db, session, catalog, edits, documents, dossiers):
        if session is None:
            raise ValueError("La exportación requiere una sesión autenticada.")
        self.db, self.catalog, self.edits = db, catalog, edits
        self._document_refs, self.dossiers = documents, dossiers

    def source_record(self, ident):
        return self.catalog[ident]

    def edit_record(self, ident):
        return self.edits.get(ident)

    def documents(self, ident=None):
        return [
            d
            for d in self._document_refs.values()
            if d.body.get("associated_ecomm_id") == ident
        ]

    def _document(self, document_id):
        return self._document_refs.get(document_id)

    def blockers(self, item, fact, **kwargs):
        if self._document(fact.get("document_id")) is None:
            return ["No está disponible el original citado por este hecho."]
        return super().blockers(item, fact, **kwargs)

    def dossier(self, ident):
        item = self.dossiers.get(ident)
        if item is None:
            raise ValueError("Falta expediente documental para esta variante.")
        reference = self.reference(ident)
        if item.identity_digest != identity_digest(reference):
            raise ValueError(
                "La identidad documental cambió; requiere revisión humana."
            )
        return SimpleNamespace(
            ecomm_id=ident,
            version=item.version,
            identity=deepcopy(reference),
            identity_digest=item.identity_digest,
            facts=deepcopy(item.facts),
            history=deepcopy(item.history),
        )


def _budget(db, ids):
    """Reject oversized originals/history BEFORE materializing ORM JSON."""
    total = 0
    for model, column, condition in (
        (
            Document,
            Document.body,
            Document.body["associated_ecomm_id"].as_string().in_(ids),
        ),
        (Dossier, Dossier.history, Dossier.ecomm_id.in_(ids)),
        (Dossier, Dossier.facts, Dossier.ecomm_id.in_(ids)),
        (Dossier, Dossier.identity, Dossier.ecomm_id.in_(ids)),
        (
            EcommApiProductEdit,
            EcommApiProductEdit.fields,
            EcommApiProductEdit.ecomm_id.in_(ids),
        ),
        (
            EcommApiProductEdit,
            EcommApiProductEdit.history,
            EcommApiProductEdit.ecomm_id.in_(ids),
        ),
    ):
        total += (
            db.scalar(
                select(
                    func.coalesce(func.sum(func.length(cast(column, Text))), 0)
                ).where(condition)
            )
            or 0
        )
        # JSON text is unicode; allow at most 4 bytes per character.
        if total * 4 > CONTEXT_BYTES:
            raise ValueError(
                "Documentos o historial exceden el presupuesto; reducí la selección."
            )


def _taxonomy_review(research, ident, edit, schedule, channel, catalog=None):
    """Consume reviewed mappings when installed; absence never means approved.

    This feature's standalone PR does not require a schema or another PR.
    The optional module is the existing taxonomy capability's public contract.
    """
    fallback = {
        "state": "UNAVAILABLE",
        "channel": channel.upper(),
        "mapping_version": 0,
        "record": None,
        "source_pair": None,
        "official_external_category_verified": False,
        "external_category_ids": None,
    }
    try:
        module = importlib.import_module("app.services.documental.taxonomy_review")
    except ModuleNotFoundError as exc:
        if exc.name != "app.services.documental.taxonomy_review":
            raise
        return fallback
    try:
        item = research.dossier(ident)
        approved, blocked = [], False
        for fact in item.facts:
            if fact.get("state") == "APPROVED":
                issues = research.blockers(item, fact)
                blocked |= bool(issues)
                if not issues:
                    approved.append(fact)
        inspection = {
            "ecomm_id": ident,
            "taxonomy_catalog": catalog,
            "conflicts": blocked
            or bool(edit and edit.source_sku != research.source_record(ident)["sku"]),
            "stale": bool(schedule["review_due"]),
            "approved_taxonomy": [
                {"field": f["field"], "value": f["value"], "evidence_id": f["id"]}
                for f in approved
                if f["field"] in {"category", "subcategory"}
            ],
            "expected": {
                "identity_hash": item.identity_digest,
                "workspace_version": edit.version if edit else 0,
                "facts": sorted(
                    (f["id"], f["version"], fact_digest(f)) for f in approved
                ),
                "documents": sorted(
                    (d.id, d.version, d.digest) for d in research.documents(ident)
                ),
            },
        }
        factory = getattr(module, "inspection_from_context", None)
        if factory:
            inspection = factory(
                ident, item,
                {"version": edit.version if edit else 0,
                 "source_sku_changed": bool(edit and edit.source_sku != research.source_record(ident)["sku"]),
                 "source": research.source_record(ident), "review_schedule": schedule},
                approved, research.documents(ident), catalog,
            )
            inspection["conflicts"] = inspection["conflicts"] or blocked
        return module.current_review(inspection, item.history, channel.upper())
    except (ValueError, KeyError):
        return {**fallback, "state": "BLOCKED"}


def _taxonomy_catalog(db):
    try:
        module = importlib.import_module("app.services.documental.taxonomy_catalog")
    except ModuleNotFoundError as exc:
        if exc.name != "app.services.documental.taxonomy_catalog":
            raise
        return None
    return module.catalog_state(db)


def _mapping_preview(mapping):
    record = mapping.get("record") or {}
    return {
        "state": mapping["state"],
        "mapping_version": mapping["mapping_version"],
        "taxonomy_revision": record.get("taxonomy_revision"),
        "catalog_bound": mapping.get("catalog_bound") is True,
        "catalog_version": record.get("catalog_version"),
        "catalog_fingerprint": record.get("catalog_fingerprint"),
        "internal_pair_id": record.get("internal_pair_id"),
        "channel_mapping_id": record.get("channel_mapping_id"),
        "source_pair": mapping.get("source_pair"),
        "internal_pair": record.get("internal_pair"),
        "target_pair": record.get("target_pair") if mapping.get("state") == "APPROVED" else None,
        "evidence_ids": record.get("evidence_ids") or [],
        "reviewer": record.get("reviewer"),
        "official_external_category_verified": False,
        "external_category_ids": None,
    }


def _identity_reasons(source, catalog):
    reasons = []
    if source.get("is_combo") is None:
        reasons.append("Falta comprobar el tipo de venta de la variante.")
    if source.get("parent_is_combo") is True and source.get("is_combo") is not True:
        reasons.append("La condición de pack del producto padre contradice la variante.")
    sku = str(source.get("sku") or "").strip().casefold()
    if not sku or sum(str(row.get("sku") or "").strip().casefold() == sku for row in catalog.values()) != 1:
        reasons.append("SKU repetido o ausente; resolver la identidad antes de preparar el canal.")
    code = source.get("gtin")
    if code:
        if not isinstance(code, str) or not _gtin_check_digit_valid(code):
            reasons.append("GTIN original inválido; revisar la identificación del producto.")
        elif sum(isinstance(row.get("gtin"), str) and bool(row["gtin"]) and _gtin_check_digit_valid(row["gtin"]) and row["gtin"].zfill(14) == code.zfill(14) for row in catalog.values()) != 1:
            reasons.append("GTIN compartido por varias variantes; revisar presentación y cantidad sin fusionarlas.")
    return reasons


def _applied_lineage(db, research, ids, edits):
    """Bounded bulk read only for noncanonical saved text needing lineage."""
    from app.services.documental.proposals import Proposals, MODEL, AI_MODEL
    from app.services.documental.channel_readiness_guard import COPY_FIELDS
    from app.services.documental.completion import MAX_APPLIED_RECORDS, MAX_LINEAGE_BYTES

    required = []
    for ident in ids:
        edit = edits.get(ident)
        if not edit:
            continue
        try:
            item = research.dossier(ident)
            approved = [fact for fact in item.facts if fact.get("state") == "APPROVED" and not research.blockers(item, fact)]
            canonical, _missing = Proposals.generate_fields(approved)
            if any((edit.fields or {}).get(key) and (edit.fields or {}).get(key) != (canonical.get(key) or {}).get("value", "") for key in COPY_FIELDS):
                required.append(Proposals.product_prefix + ident)
        except (ValueError, KeyError):
            continue
    result = {ident: [] for ident in ids}
    if not required:
        return result
    condition = (
        KikiAiEditorialDraft.product_key.in_(required),
        KikiAiEditorialDraft.review_status == "APPLIED",
        KikiAiEditorialDraft.model.in_((MODEL, AI_MODEL)),
    )
    counts = db.execute(select(KikiAiEditorialDraft.product_key, func.count()).where(*condition).group_by(KikiAiEditorialDraft.product_key)).all()
    if any(count > MAX_APPLIED_RECORDS for _key, count in counts):
        raise ValueError("El historial de propuestas excede el límite de revisión; acotá la selección.")
    size = db.scalar(select(func.coalesce(func.sum(
        func.length(cast(KikiAiEditorialDraft.history, Text)) + func.length(cast(KikiAiEditorialDraft.source_facts, Text))
    ), 0)).where(*condition)) or 0
    if size * 4 > MAX_LINEAGE_BYTES:
        raise ValueError("La trazabilidad de propuestas supera el presupuesto; no se recortaron evidencias.")
    records = db.scalars(select(KikiAiEditorialDraft).options(load_only(
        KikiAiEditorialDraft.id, KikiAiEditorialDraft.product_key, KikiAiEditorialDraft.model,
        KikiAiEditorialDraft.review_status, KikiAiEditorialDraft.history, KikiAiEditorialDraft.source_facts,
    )).where(*condition).order_by(KikiAiEditorialDraft.id.desc()))
    for record in records:
        result[record.product_key.removeprefix(Proposals.product_prefix)].append(record)
    return result


def preview_commercial_export(db, session, channel, ids):
    if channel not in {"ml", "tn"}:
        raise ValueError("Canal de exportación inválido.")
    if (
        not isinstance(ids, list)
        or not 1 <= len(ids) <= MAX_ITEMS
        or len(set(ids)) != len(ids)
        or not all(isinstance(i, str) and valid_variant_id(i) for i in ids)
    ):
        raise ValueError("Seleccioná entre 1 y 20 Ecomm ID únicos y válidos.")
    if session is None:
        raise ValueError("La exportación requiere una sesión autenticada.")
    catalog = sources(db, lock=True)
    if any(ident not in catalog for ident in ids):
        raise ValueError("Una variante ya no está en la captura API completa.")
    _budget(db, ids)
    edits = {
        e.ecomm_id: e
        for e in db.scalars(
            select(EcommApiProductEdit)
            .where(EcommApiProductEdit.ecomm_id.in_(ids))
            .order_by(EcommApiProductEdit.ecomm_id)
            .with_for_update(read=True)
        )
    }
    # Same ordering as commercial saves: source, commercial rows, documentary
    # mutex. This prevents a concurrent revocation during fingerprint/output.
    if (
        db.scalar(select(Control).where(Control.id == 1).with_for_update(read=True))
        is None
    ):
        raise ValueError("Falta el control documental; exportación bloqueada.")
    docs = {
        d.id: d
        for d in db.scalars(
            select(Document)
            .options(
                load_only(Document.id, Document.version, Document.digest, Document.body)
            )
            .where(Document.body["associated_ecomm_id"].as_string().in_(ids))
        )
    }
    dossiers = {
        d.ecomm_id: d
        for d in db.scalars(select(Dossier).where(Dossier.ecomm_id.in_(ids)))
    }
    research = ReadOnlyResearch(db, session, catalog, edits, docs, dossiers)
    taxonomy_catalog = _taxonomy_catalog(db)
    lineage = _applied_lineage(db, research, ids, edits)
    items = []
    for ident in ids:
        source, edit = catalog[ident], edits.get(ident)
        fields = (
            {**blank_fields(), **dict(edit.fields or {})} if edit else blank_fields()
        )
        schedule = review_schedule(edit)
        reasons = _identity_reasons(source, catalog)
        if not edit or edit.status != "READY_FOR_CHANNELS":
            reasons.append(
                "La ficha no tiene aprobación editorial interna para canales."
            )
        if edit and edit.source_sku != source["sku"]:
            reasons.append("Cambió el SKU del Ecomm ID; resolver identidad.")
        if source.get("identity_blockers"):
            reasons.append("Códigos originales contradictorios; resolver identidad.")
        if not _readiness(fields)["ready"]:
            reasons.append("La ficha comercial está incompleta.")
        if schedule["review_reason"] != "CURRENT":
            reasons.append("Falta revisión mensual vigente de la ficha.")
        internal_mapping = _taxonomy_review(research, ident, edit, schedule, "kiki", taxonomy_catalog)
        mapping = _taxonomy_review(research, ident, edit, schedule, channel, taxonomy_catalog)
        evidence = None
        try:
            evidence = require_primary_evidence(
                db, session, ident, fields, research=research, strict_stage4=True,
                applied_proposals=lineage[ident], taxonomy=internal_mapping,
            )
        except ValueError as exc:
            reasons.append(str(exc))
        internal = _mapping_preview(internal_mapping)
        target_mapping = _mapping_preview(mapping)
        if internal["state"] != "APPROVED" or not internal["catalog_bound"]:
            reasons.append("Falta una clasificación interna KIKI aprobada y vigente en la taxonomía versionada.")
        internal_pair = internal["target_pair"] or {}
        if internal_pair.get("category") != fields["category"] or internal_pair.get("subcategory") != fields["subcategory"]:
            reasons.append("La categoría y subcategoría guardadas no coinciden con la clasificación interna aprobada.")
        if target_mapping["state"] != "APPROVED" or not target_mapping["catalog_bound"]:
            reasons.append("Falta una equivalencia aprobada y vigente para este canal.")
        if internal["internal_pair_id"] != target_mapping["internal_pair_id"] or internal["catalog_fingerprint"] != target_mapping["catalog_fingerprint"]:
            reasons.append("El mapeo del canal no corresponde a la misma clasificación interna y versión de catálogo.")
        items.append(
            {
                "ecomm_id": ident,
                "sku": source["sku"],
                "name": source["product_name"],
                "source_presentation": source.get("variant_description"),
                "source_is_combo": source.get("is_combo"),
                "source_parent_is_combo": source.get("parent_is_combo"),
                "barcode_original": source.get("barcode"),
                "gtin_original": source.get("gtin_raw"),
                "captured_at": source.get("captured_at"),
                "workspace_version": edit.version if edit else 0,
                "editorial_status": edit.status if edit else "NOT_STARTED",
                "review_schedule": schedule,
                "evidence_verified": evidence is not None,
                "document_id": evidence["document_id"] if evidence else None,
                "document_sha256": evidence["document_sha256"] if evidence else None,
                "commercial_fields": {k: deepcopy(fields[k]) for k in CONTENT_FIELDS},
                "source_urls": sorted(
                    {s["url"] for s in fields["sources"] if s.get("url")}
                ),
                "prepared_internal": not reasons,
                "state": "PREPARED_FOR_HUMAN_CHANNEL_REVIEW"
                if not reasons
                else "BLOCKED",
                "blockers": reasons,
                "internal_taxonomy": internal,
                "channel_taxonomy": target_mapping,
                "field_evidence": (evidence or {}).get("commercial_coverage", {}).get("field_evidence", {}),
                "field_lineage": (evidence or {}).get("commercial_coverage", {}).get("field_lineage", {}),
                "channel_requirements_pending": (
                    ["Revisar o revalidar la equivalencia taxonómica para este canal."]
                    if mapping.get("state") != "APPROVED"
                    else []
                )
                + [
                    "Verificar los identificadores oficiales y el formato vigente del canal antes de cualquier importación o publicación."
                ],
                "publication_enabled": False,
            }
        )
    fingerprint = digest(
        {
            "channel": channel,
            "items": items,
            "taxonomy_catalog": taxonomy_catalog,
            "dossiers": sorted(
                (
                    d.ecomm_id,
                    d.version,
                    d.identity_digest,
                    digest(d.facts),
                    digest(d.history),
                )
                for d in dossiers.values()
            ),
            "documents": sorted(
                (d.id, d.version, d.digest, digest(d.body)) for d in docs.values()
            ),
            "editorial_history": sorted(
                (e.ecomm_id, digest(e.history)) for e in edits.values()
            ),
        }
    )
    result = {
        "mode": "READ_ONLY_COMMERCIAL_REVIEW_PACKAGE",
        "channel": channel,
        "source": "ECOMM_APP_API_STAGE",
        "preview_fingerprint": fingerprint,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(items),
        "prepared_internal": sum(i["prepared_internal"] for i in items),
        "blocked": sum(not i["prepared_internal"] for i in items),
        "items": items,
        "native_provider_import_file": False,
        "external_writes_enabled": False,
        "provider_calls": 0,
        "ai_requests": 0,
    }
    if len(json.dumps(result, ensure_ascii=False).encode()) > MAX_BYTES:
        raise ValueError("La previsualización supera 10 MiB; reducí la selección.")
    return result


def download_commercial_export(db, session, channel, ids, expected_fingerprint):
    preview = preview_commercial_export(db, session, channel, ids)
    _check_fingerprint(expected_fingerprint, preview["preview_fingerprint"])
    out = StringIO(newline="")
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(
        [
            "canal",
            "ecomm_id",
            "sku",
            "nombre_api",
            "presentacion_api",
            "combo_api",
            "estado_revision",
            "bloqueos",
            "requisitos_canal_pendientes",
            "version_ficha",
            "captura_api",
            "ultima_revision",
            "documento_original_sha256",
            "estado_taxonomia_canal",
            "version_mapeo_canal",
            "revision_taxonomia",
            "categoria_canal_revisada",
            "subcategoria_canal_revisada",
            "hechos_taxonomia",
            "version_catalogo_taxonomia",
            "par_interno_id",
            "mapeo_canal_id",
            "evidencias_por_campo",
            "linaje_por_campo",
            *CONTENT_FIELDS,
            "fuentes_documentales",
            "publicacion_habilitada",
            "formato_nativo_proveedor",
        ]
    )
    for item in preview["items"]:
        values = [
            channel,
            item["ecomm_id"],
            item["sku"],
            item["name"],
            item["source_presentation"],
            item["source_is_combo"],
            item["state"],
            " | ".join(item["blockers"]),
            " | ".join(item["channel_requirements_pending"]),
            item["workspace_version"],
            item["captured_at"],
            item["review_schedule"]["last_review_at"],
            item["document_sha256"],
        ]
        taxonomy = item["channel_taxonomy"]
        target = taxonomy["target_pair"] or {}
        values.extend(
            [
                taxonomy["state"],
                taxonomy["mapping_version"],
                taxonomy["taxonomy_revision"],
                target.get("category"),
                target.get("subcategory"),
                " | ".join(taxonomy["evidence_ids"]),
                taxonomy["catalog_version"],
                taxonomy["internal_pair_id"],
                taxonomy["channel_mapping_id"],
                json.dumps(item["field_evidence"], ensure_ascii=False),
                json.dumps(item["field_lineage"], ensure_ascii=False),
            ]
        )
        values.extend(
            json.dumps(item["commercial_fields"][k], ensure_ascii=False)
            if isinstance(item["commercial_fields"][k], list)
            else item["commercial_fields"][k]
            for k in CONTENT_FIELDS
        )
        values.extend([" | ".join(item["source_urls"]), "NO", "NO"])
        writer.writerow([_cell(v) for v in values])
    data = ("\ufeff" + out.getvalue()).encode("utf-8")
    if len(data) > MAX_BYTES:
        raise ValueError("El CSV supera 10 MiB; no se exportó un archivo parcial.")
    return data, preview


def download_monthly_report(db, expected_fingerprint):
    summary, rows = build_delivery_audit(db)
    _check_fingerprint(expected_fingerprint, summary["preview_fingerprint"])
    return export_delivery_csv(rows).encode("utf-8"), summary
