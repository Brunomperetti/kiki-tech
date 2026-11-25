"""Local Mercado Libre preflight, not a valid /items request.

Legacy approvals use a different identity scheme; never transfer them by SKU.
The official category, attributes and selling terms must be verified separately.
"""
from app.services.commercial_channel_export_service import preview_commercial_export


def local_preview(db, session, ecomm_id):
    review = preview_commercial_export(db, session, "ml", [ecomm_id])
    item = review["items"][0]
    fields = item["commercial_fields"]
    blockers = list(item["blockers"])
    mapping = item["channel_taxonomy"]
    if mapping["state"] != "APPROVED":
        blockers.append("Falta equivalencia taxonómica aprobada para Mercado Libre.")
    checks_pending = [
        "Identidad y duplicados de la cuenta Mercado Libre.",
        "Categoría oficial y modalidad de publicación vigentes.",
        "Atributos obligatorios y condicionales para el producto exacto.",
        "Imágenes autorizadas y aptas para el canal.",
        "Precio, moneda, cantidad, condición y condiciones de venta.",
        "Validación oficial del payload y aprobación humana final.",
    ]
    return {
        "ecomm_id": ecomm_id,
        "sku": item["sku"],
        "workspace_version": item["workspace_version"],
        "preview_fingerprint": review["preview_fingerprint"],
        "commercial_preview": {
            "title": fields["title"],
            "description": fields["description"],
            "brand": fields["brand"],
        },
        "local_blockers": blockers,
        "channel_checks_pending": checks_pending,
        "official_category_verified": False,
        "official_payload_validated": False,
        "external_writes_enabled": False,
        "provider_calls": 0,
    }
