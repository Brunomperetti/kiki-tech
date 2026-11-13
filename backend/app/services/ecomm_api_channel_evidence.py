"""API-identity review over existing captures/decision models; no provider I/O."""

from datetime import datetime, timezone
import hashlib
import json
import re

from sqlalchemy import select
from ..core.config import get_settings
from ..database.models import InventoryLinkageDecision, TiendanubeMatchDecision
from ..integrations.ecomm_app.api_catalog_browser import api_variant_row
from .tiendanube_assisted_match_service import normalize, pack_units, variant_conflict
from .ecomm_api_product_workspace_service import _gtin_check_digit_valid

PROFILE = "API_VARIANT_CHANNEL_REVIEW_V1"
TN_FRESH_HOURS = 24  # Local review policy, never proof of current TN publication.
STATES = {
    "CONFIRMED_CAPTURE",
    "CANDIDATE",
    "PENDING_VALIDATION",
    "INSUFFICIENT_EVIDENCE",
    "STALE",
    "IDENTITY_CONFLICT",
    "VERIFIED_LINK",
}


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def quantity(value):
    found = re.findall(
        r"\b(?:pack\s*(?:de\s*)?x?|combo\s*x?|x)\s*(\d+)\b", str(value).casefold()
    )
    return int(found[0]) if len(set(found)) == 1 else None


def row_key(channel, row):
    if channel == "ml":
        return str(row.get("external_id") or "").strip()
    return fingerprint([row.get("slug"), row.get("sku")]) if row.get("slug") else ""


def decision_key(channel, row):
    key = row_key(channel, row)
    # Keep old records/consumers intact; same existing tables, separate API provenance.
    return ("API_ML:" if channel == "ml" else "API_TN:") + key if key else ""


def load_reviews(db):
    ml = list(db.scalars(select(InventoryLinkageDecision)))
    tn = list(db.scalars(select(TiendanubeMatchDecision)))
    return {
        "ml": {d.external_id: d for d in ml},
        "tn": {d.source_key: d for d in tn},
        "legacy_ignored": sum(not d.external_id.startswith("API_ML:") for d in ml)
        + sum(not d.source_key.startswith("API_TN:") for d in tn),
    }


def age_info(value, channel, now):
    hours = (
        get_settings().ml_snapshot_fresh_hours if channel == "ml" else TN_FRESH_HOURS
    )
    try:
        date = datetime.fromisoformat(value)
        if not date.tzinfo:
            date = date.replace(tzinfo=timezone.utc)
        age = (now - date).total_seconds() / 3600
        fresh = 0 <= age <= hours
    except (TypeError, ValueError):
        age, fresh = None, False
    return {
        "fresh": fresh,
        "age_hours": round(age, 2) if age is not None else None,
        "review_after_hours": hours,
    }


def source_identity(parent, variant, captured_at, edit):
    source = api_variant_row(parent, variant, captured_at)
    fields = edit.fields if edit else {}
    return {
        **source,
        "brand": fields.get("brand") or parent.get("brand"),
        "brand_origin": "KIKI_EDITORIAL"
        if fields.get("brand")
        else "API_CAPTURE"
        if parent.get("brand")
        else "UNKNOWN",
    }


def enrich(base, channel, rows, identity, reviews, now):
    age = age_info(base["snapshot_at"], channel, now)
    title_key = "title" if channel == "ml" else "name"
    candidates = []
    key_counts = reviews["row_counts"][channel]
    for row in rows[:8]:
        key = row_key(channel, row)
        record = reviews[channel].get(decision_key(channel, row))
        target = (
            (record.product_snapshot if channel == "ml" else record.target_snapshot)
            if record
            else {}
        )
        source = record.source_snapshot if record else {}
        revision = len(record.history or []) if record else 0
        state = (
            (record.decision if channel == "ml" else record.status) if record else None
        )
        variant_id = (
            (record.ecomm_id if channel == "ml" else record.target_ecomm_id)
            if record
            else None
        )
        token = fingerprint(
            {
                "identity": identity,
                "row": row,
                "snapshot_at": base["snapshot_at"],
                "source": base["source"],
            }
        )
        api_review = bool(
            record
            and source.get("profile") == PROFILE
            and target.get("ecomm_id") == identity["ecomm_id"]
            and variant_id == identity["ecomm_id"]
        )
        current = bool(api_review and source.get("fingerprint") == token)
        verified = bool(current and state == "APPROVED")
        blockers = list(identity.get("identity_blockers") or [])
        if not key or (channel == "ml" and len(key) > 70) or key_counts[key] != 1:
            blockers.append(
                "Identificador de canal ausente o repetido; no permite validar una fila única."
            )
        if channel == "ml" and not re.fullmatch(
            r"MLA[1-9][0-9]*(?:#[1-9][0-9]*)?", key
        ):
            blockers.append(
                "Identificador ML no verificable en el formato del contrato."
            )
        if (
            type(identity.get("is_combo")) is bool
            and type(identity.get("parent_is_combo")) is bool
            and identity["is_combo"] != identity["parent_is_combo"]
        ):
            blockers.append(
                "Las marcas de combo de producto y variante difieren; requieren revisión de origen."
            )
        if (
            not identity.get("variant_description")
            or type(identity.get("is_combo")) is not bool
        ):
            blockers.append(
                "Presentación o condición de combo desconocida en la variante API."
            )
        actual_name = str(row.get(title_key) or "")
        expected_name = f"{identity.get('product_name') or ''} {identity.get('variant_description') or ''}"
        if not actual_name or variant_conflict(
            expected_name, identity.get("sku"), actual_name, row.get("sku")
        ):
            blockers.append("Nombre/presentación de canal ausente o incompatible.")
        expected_units, actual_units = (
            pack_units(identity.get("variant_description")),
            pack_units(actual_name),
        )
        if not expected_units or not actual_units or expected_units != actual_units:
            blockers.append(
                "Contenido/presentación sin contraste explícito suficiente."
            )
        brand = str(identity.get("brand") or "")
        if (
            not brand
            or not row.get("brand")
            or normalize(brand) != normalize(row["brand"])
        ):
            blockers.append(
                "Marca ausente o diferente; completar el contraste antes de validar."
            )
        gtin = row.get("ean_raw") or row.get("ean")
        if identity.get("gtin") and gtin and str(identity["gtin"]) != str(gtin):
            blockers.append("GTIN de canal diferente del código de la variante API.")
        if gtin and not _gtin_check_digit_valid(str(gtin)):
            blockers.append(
                "Código de canal inválido; requiere revisión de su documentación."
            )
        actual_qty = quantity(actual_name)
        source_qty = quantity(identity.get("variant_description"))
        if identity.get("is_combo") is True and (
            not source_qty or source_qty != actual_qty
        ):
            blockers.append("Pack sin composición/cantidad coincidente y explícita.")
        if identity.get("is_combo") is False and actual_qty not in (None, 1):
            blockers.append("El canal describe un pack y la variante API no es combo.")
        if record and variant_id != identity["ecomm_id"] and state == "APPROVED":
            blockers.append(
                "La fila está validada para otro Ecomm ID; primero requiere revisión/revocación de su vinculación."
            )
        if not age["fresh"]:
            blockers.append(
                "Captura desactualizada o sin fecha vigente; no se puede confirmar publicación."
            )
        if verified and blockers:
            verified = False
        candidates.append(
            {
                "id": key,
                "slug": row.get("slug") if channel == "tn" else None,
                "token": token,
                "title": actual_name or None,
                "sku": row.get("variant_sku")
                or row.get("sku_effective")
                or row.get("sku"),
                "barcode": row.get("barcode"),
                "gtin": gtin,
                "brand": row.get("brand"),
                "listing_status": row.get("status") if channel == "ml" else None,
                "presentation_units": sorted([list(v) for v in actual_units]),
                "quantity_in_title": actual_qty,
                "identity_verified": verified,
                "review_state": state if api_review else None,
                "review_current": current,
                "revision": revision,
                "history": record.history if api_review else [],
                "blockers": blockers,
                "can_review": not blockers,
            }
        )
    linked = [c for c in candidates if c["identity_verified"]]
    confirmed = [
        c
        for c in linked
        if channel == "ml" and c["listing_status"] == "active" and age["fresh"]
    ]
    hard_conflict = bool(identity.get("identity_blockers")) or base["status"] in {
        "GTIN_CONFLICT",
        "PRESENTATION_CONFLICT",
    }
    state = (
        "IDENTITY_CONFLICT"
        if hard_conflict
        else "STALE"
        if base["snapshot_available"] and not age["fresh"]
        else "CONFIRMED_CAPTURE"
        if confirmed
        else "VERIFIED_LINK"
        if linked
        else "PENDING_VALIDATION"
        if base["status"] in {"AMBIGUOUS_API_SKU", "MULTIPLE_SKU_ROWS", "PACK_REVIEW"}
        or any(c["review_state"] for c in candidates)
        else "CANDIDATE"
        if candidates
        else "INSUFFICIENT_EVIDENCE"
    )
    note = {
        "CONFIRMED_CAPTURE": "Vínculo revisado por Ecomm ID y publicación activa en esa captura ML; no es una consulta en vivo.",
        "VERIFIED_LINK": "Vinculación revisada. El CSV no demuestra publicación actual."
        if channel == "tn"
        else "Vínculo revisado, sin publicación activa confirmada en la captura.",
        "IDENTITY_CONFLICT": "Conflicto de identidad; no se confirma publicación ni se fusionan variantes.",
        "STALE": "La captura perdió vigencia para esta revisión. No se puede inferir el estado actual.",
        "PENDING_VALIDATION": "Relación pendiente de validación por variante, presentación y cantidad.",
        "CANDIDATE": "Coincidencia candidata; no acredita una vinculación ni publicación confirmada.",
        "INSUFFICIENT_EVIDENCE": "Sin evidencia suficiente; no significa que el producto no esté publicado.",
    }[state]
    return {
        **base,
        "evidence_state": state,
        "identity_verified": bool(linked),
        "confirmed_listing": bool(confirmed),
        "confirmed_listing_count": len(confirmed),
        "publication_observable": channel == "ml" and base["snapshot_available"],
        "freshness": age,
        "candidates": candidates,
        "candidates_total": len(rows),
        "note": note,
        "legacy_decisions_ignored": reviews["legacy_ignored"],
        "scope": "CAPTURE_ONLY"
        if channel == "ml"
        else "CSV_IMPORT_ONLY_NO_CURRENT_PUBLICATION",
    }
