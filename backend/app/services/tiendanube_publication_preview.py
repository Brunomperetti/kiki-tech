"""Local-only preflight for a single hidden Tiendanube product.

This module deliberately exposes no external mutation workflow.
"""
from collections import Counter

from app.services.commercial_channel_export_service import preview_commercial_export
from app.services.editorial_batches.context import sources


def normalized_sku(value):
    return value.strip().casefold() if isinstance(value, str) else ""


def duplicate_candidates(client, sku, *, max_pages=100):
    """Bounded complete scan; never mistake an incomplete scan for absence."""
    target = normalized_sku(sku)
    if not target:
        raise ValueError("SKU obligatorio")
    seen = set()
    matches = []
    for page in range(1, max_pages + 1):
        rows = client.list_products(page=page, per_page=100)
        if len(rows) > 100:
            raise ValueError("Paginación de Tiendanube incompatible.")
        for product in rows:
            ident = product.get("id")
            if type(ident) is not int or ident <= 0 or ident in seen:
                raise ValueError("Inventario remoto inconsistente; revisar antes de continuar.")
            seen.add(ident)
            variants = product.get("variants")
            if not isinstance(variants, list) or not variants:
                raise ValueError("Respuesta sin variantes; no se puede descartar duplicados.")
            for variant in variants:
                if not isinstance(variant, dict) or "sku" not in variant:
                    raise ValueError("Variante remota sin datos de SKU.")
                if normalized_sku(variant["sku"]) == target:
                    matches.append({"product_id": ident, "variant_id": variant.get("id")})
        if len(rows) < 100:
            return matches
    raise ValueError("No se completó la lectura remota; no crear un producto.")


def local_preview(db, session, ecomm_id):
    review = preview_commercial_export(db, session, "tn", [ecomm_id])
    item = review["items"][0]
    fields = item["commercial_fields"]
    blockers = list(item["blockers"])
    sku = normalized_sku(item["sku"])
    counts = Counter(normalized_sku(source.get("sku")) for source in sources(db).values())
    if not sku or counts[sku] != 1:
        blockers.append("SKU Ecomm-App ausente o repetido.")
    if item["source_is_combo"] is not False or item["source_parent_is_combo"] is not False:
        blockers.append("El piloto no admite packs ni identidad de pack indeterminada.")
    if item["channel_taxonomy"]["state"] != "APPROVED":
        blockers.append("Falta equivalencia taxonómica aprobada.")
    if not all(isinstance(fields.get(key), str) and fields[key].strip()
               for key in ("title", "description")):
        blockers.append("Título o descripción sin completar.")
    return {
        "ecomm_id": ecomm_id,
        "sku": item["sku"],
        "workspace_version": item["workspace_version"],
        "preview_fingerprint": review["preview_fingerprint"],
        "payload_preview": {
            "name": {"es": fields["title"]},
            "description": {"es": fields["description"]},
            "visibility": "hidden",
            "variants": [{"sku": item["sku"]}],
        },
        "local_blockers": blockers,
        "remote_duplicate_check": "NOT_RUN",
        "external_writes_enabled": False,
        "provider_calls": 0,
        "notice": "Previsualización parcial: faltan conexión, verificación remota y registro persistente de envío.",
    }
