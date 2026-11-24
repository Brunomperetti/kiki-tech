"""Explicit, bounded manufacturer-document intake from a reviewed sitemap preview.

This is not a crawler or an autonomous approval pipeline. The operator
confirms one or two unambiguous candidate URLs from a specific sitemap hash.
HTML originals are archived as PENDING evidence, atomically; no facts, edits,
vendor data, prices, images or channel publications are approved or written.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import select

from app.services.documental.contracts import Incorporate
from app.services.documental.local_documents import LocalDocuments, parse_local
from app.services.documental.storage import Dossier, Document
from app.services.editorial_batches.context import AtomicSession, sources
from .sitemap_discovery import preview_candidates
from .source_fetch import fetch_html

MAX_IMPORT = 2
MAX_HTML_BYTES = 4 * 1024 * 1024


def _identity(row):
    """Typed, JSON-roundtrippable identity, never stock or editorial overlays.

    Keep raw codes as well as their compatibility projection: a changed
    barcode must not hide behind an unchanged ``gtin``. Flat type tags prevent
    False, 0, None and empty text from becoming the same persisted signature.
    Previously persisted narrower signatures fail closed and need review.
    """
    values = []
    for key in (
        "ecomm_id", "sku", "parent_code", "product_name",
        "variant_description", "gtin", "barcode", "gtin_raw",
        "is_combo", "parent_is_combo", "identity_blockers", "brand", "manufacturer",
    ):
        value = row.get(key)
        values.extend((
            type(value).__name__,
            value if value is None or type(value) in (str, bool, int)
            else json.dumps(value, sort_keys=True, ensure_ascii=False),
        ))
    return tuple(values)


def _eligible_unit(row):
    """A false variant flag cannot override an explicit pack parent/conflict."""
    if (
        not row or not isinstance(row.get("sku"), str) or not row["sku"].strip()
        or row.get("is_combo") is not False
        or row.get("parent_is_combo") not in (None, False)
        or type(row.get("parent_is_combo")) not in (type(None), bool)
        or row.get("identity_blockers")
    ):
        return False
    codes = [row.get(key) for key in ("barcode", "gtin_raw", "gtin")]
    if any(code is not None and not isinstance(code, str) for code in codes):
        return False
    return len({code for code in codes if code}) <= 1


def _reject_duplicate_original(documents, checksum):
    """Same variant/bytes under another URL is review work, not a new source.

    Call only with the exact variant's documents under the documentary mutex.
    Do not relabel an existing original or transfer its human approvals.
    """
    if any(
        (doc.body.get("original") or {}).get("sha256") == checksum
        for doc in documents
    ):
        raise ValueError(
            "El mismo original SHA-256 ya está archivado para esta variante; "
            "revisá la fuente existente sin duplicar ni transferir decisiones."
        )


def preflight(preview, items, sitemap_sha256):
    """Reject ambiguity, mismatched URLs and a modified sitemap before fetch."""
    receipt = preview.get("receipt") or {}
    if receipt.get("sitemap_sha256") != sitemap_sha256:
        raise ValueError(
            "El sitemap cambió desde la vista previa. Volvé a investigar las fuentes."
        )
    mapped = {entry["ecomm_id"]: entry for entry in preview["items"]}
    if len(mapped) != len(items):
        raise ValueError("Selección duplicada o no coincide con el índice.")
    for item in items:
        found = mapped.get(item["ecomm_id"])
        if (
            not found or found["state"] != "CANDIDATES"
            or found["ambiguous"] or found["candidate_count"] != 1
            or len(found["candidates"]) != 1
            or found["candidates"][0]["url"] != item["url"]
            or found["candidates"][0]["verified"] is not False
            or found["candidates"][0]["review_required"] is not True
        ):
            raise ValueError(
                "Coincidencia ambigua, bloqueada o distinta de la vista previa; "
                "no se descargaron páginas de producto."
            )
    return mapped


def capture_selected(
    db, session, *, sitemap_url, sitemap_sha256, items, configured_hosts,
    previewer=preview_candidates, downloader=fetch_html, parser=parse_local,
):
    """Import up to two originals, all-or-nothing, after rechecking the sitemap.

    Network and isolated parsing occur *before* acquiring the evidence mutex;
    a second API capture/identity check and dossier-version CAS prevent stale
    writes if the catalogue or an operator changed during those steps.
    """
    if not 1 <= len(items) <= MAX_IMPORT:
        raise ValueError("Cada paso admite una o dos variantes.")
    ids = [entry["ecomm_id"] for entry in items]
    if len(ids) != len(set(ids)):
        raise ValueError("No se admite repetir Ecomm ID en el mismo paso.")
    if any(
        not isinstance(entry["url"], str)
        or len(entry["url"]) > 1000
        or not entry["url"].startswith("https://")
        for entry in items
    ):
        raise ValueError("URL de fabricante inválida.")

    initial_rows = sources(db)
    selected = {}
    for ident in ids:
        row = initial_rows.get(ident)
        if not _eligible_unit(row):
            raise ValueError(
                "Ecomm ID, SKU o tipo de venta no es válido para capturar documentos."
            )
        selected[ident] = _identity(row)

    expected_versions = {}
    for item in items:
        ident = item["ecomm_id"]
        # Skip expensive external GETs for URLs already archived for this
        # exact variant. Keep the post-lock check below for concurrent writes.
        archived = db.scalar(
            select(Document.id)
            .where(Document.body["associated_ecomm_id"].as_string() == ident)
            .where(Document.body["source"]["reference_url"].as_string() == item["url"])
            .limit(1)
        )
        if archived:
            raise ValueError(
                "Ya existe documentación para esta URL y variante. "
                "Revisá la evidencia existente en vez de duplicarla."
            )
        version = db.scalar(select(Dossier.version).where(Dossier.ecomm_id == ident))
        expected_versions[ident] = version if version is not None else 0

    preview = previewer(db, ids, sitemap_url, configured_hosts)
    preflight(preview, items, sitemap_sha256)

    prepared = []
    # The operator has explicitly selected these exact same-host URLs.
    # Each GET must pass public DNS, pinned TLS, robots.txt and no-redirect.
    for item in items:
        original, trace = downloader(
            item["url"], configured_hosts, max_bytes=MAX_HTML_BYTES
        )
        if not original or len(original) > MAX_HTML_BYTES:
            raise ValueError("Documento excede el límite de 4 MiB.")
        if trace.get("sha256") != sha256(original).hexdigest():
            raise ValueError("El SHA-256 recibido no coincide con el original.")
        imported = Incorporate(
            kind="FILE",
            web_snapshot=True,
            expected_version=expected_versions[item["ecomm_id"]],
            filename="fabricante-" + trace["sha256"][:16] + ".html",
            content_type="text/html",
            content_base64=base64.b64encode(original).decode("ascii"),
            provenance_note=(
                "HTML original obtenido automáticamente desde el índice de "
                "productos autorizado; identidad y procedencia pendientes de "
                "revisión humana."
            ),
            reference_url=item["url"],
            declared_official=False,
            declared_consulted_at=datetime.now(timezone.utc),
            authorized_local_processing=True,
        )
        parsed = parser(imported)
        prepared.append((item, imported, parsed, {
            **trace,
            "sitemap_url": sitemap_url,
            "sitemap_sha256": sitemap_sha256,
            "selection_mode": "EXPLICIT_BATCH_MAX_2",
            "mode": "ALLOWLISTED_EXPLICIT_BATCH",
        }))

    # Re-read source snapshot under a shared lock, then use the already
    # established documentary mutex. All database commits stay atomic.
    db.expire_all()
    refreshed = sources(db, lock=True)
    if any(
        not _eligible_unit(refreshed.get(ident))
        or _identity(refreshed.get(ident) or {}) != selected[ident]
        for ident in ids
    ):
        raise ValueError(
            "Ecomm-App cambió mientras se consultaban fuentes; no se importó nada."
        )
    atomic = AtomicSession(db)
    imported = []
    for item, body, parsed, trace in prepared:
        documents = LocalDocuments(atomic, session)
        # The Research constructor obtains the documentary transaction mutex.
        dossier = documents.research.dossier(item["ecomm_id"])
        documents.research.expect(dossier, body.expected_version)
        # No silent replacement/re-import of a previously reviewed original.
        existing_documents = documents.research.documents(item["ecomm_id"])
        if any(
            doc.body.get("source", {}).get("reference_url") == item["url"]
            for doc in existing_documents
        ):
            raise ValueError(
                "Ya existe documentación para esta URL y variante. "
                "Revisá la evidencia existente en vez de duplicarla."
            )
        _reject_duplicate_original(existing_documents, trace["sha256"])
        result = documents.incorporate(
            item["ecomm_id"], body, parsed, source_retrieval=trace,
        )
        imported.append({
            "ecomm_id": item["ecomm_id"],
            "document_id": result["incorporated_document_id"],
            "review_state": "PENDING",
            "facts_approved": 0,
            "url": item["url"],
        })
    db.commit()
    return {
        "mode": "EXPLICIT_BATCH_SOURCE_INTAKE",
        "sitemap_sha256": sitemap_sha256,
        "documents": imported,
        "originals_archived": len(imported),
        "facts_approved": 0,
        "external_catalogue_writes": 0,
        "openai_requests": 0,
        "policy": "Las fuentes incorporadas requieren revisión individual de identidad, procedencia y hechos.",
    }
