"""Client-reported Hileret references; no original brochure bytes or API identity."""

EAN = "7794940000796"
DUN = "97794940000799"
URL = "https://descargas.hileret.com.ar/Hileret/Folleto%20Ventas%20Hileret%2017x25_400s.pdf"
UNIT_ID = "PILOT-HILERET-200-UNIT-SYNTHETIC"
PACK_ID = "PILOT-HILERET-200-PACK6-SYNTHETIC"
PILOTS = {
    UNIT_ID: {
        "name": "Edulcorante líquido con Stevia Hileret",
        "presentation": "200 ml",
        "is_combo": False,
        "sale_units": 1,
        "excel_row": 28,
        "excel_presentation": "200 cc",
    },
    PACK_ID: {
        "name": "Pack x6 Hileret Stevia líquido",
        "presentation": "6 x 200 ml",
        "is_combo": True,
        "sale_units": 6,
        "excel_row": 27,
        "excel_presentation": "Pack x6 de 200 ml",
    },
}
SOURCE_EVENT = "HILERET_PILOT_REFERENCE_REGISTERED"
REQUESTED_FIELDS = (
    "title",
    "short_description",
    "description",
    "details",
    "presentation",
    "category",
    "subcategory",
    "seo_title",
    "seo_description",
)


def references(ident):
    pilot = PILOTS[ident]
    return {
        "test_id": ident,
        "test_id_is_synthetic": True,
        "authentic_ecomm_id": None,
        "binding_status": "PENDING",
        "excel": {
            "file_name": "productos.xlsx",
            "row": pilot["excel_row"],
            "name": pilot["name"],
            "presentation": pilot["excel_presentation"],
            "ean_declared": EAN,
            "source_kind": "CLIENT_AUXILIARY_REFERENCE",
            "source": "Datos comunicados por el usuario; no lectura local del Excel ni captura Ecomm-App.",
            "cells": None,
        },
        "brochure": {
            "url": URL,
            "domain": "descargas.hileret.com.ar",
            "reported_page": 2,
            "reported_brand": "Hileret",
            "reported_product": "Hileret Stevia",
            "reported_unit_volume": "200 ml",
            "reported_unit_ean": EAN,
            "reported_logistic_units": 9,
            "reported_logistic_dun": DUN,
            "source": "Folleto oficial informado por el usuario; contenido no consultado ni procesado por Codex.",
            "original_available_at_registration": False,
            "document_sha256_at_registration": None,
            "consulted_at": None,
            "network_enabled": False,
        },
        "sale_units": pilot["sale_units"],
        "other_test_id": PACK_ID if ident == UNIT_ID else UNIT_ID,
        "missing_evidence": [
            "PDF original autorizado: bytes, SHA-256, revisión de procedencia y citas ubicadas en página 2.",
            "EAN, marca y volumen individual: contrastar con el original; checksum no acredita correspondencia.",
            "Pack comercial x6: respaldo específico del pack; el EAN compartido no vincula ni fusiona variantes.",
            "Caja logística x9 y DUN: nunca convertirlos en presentación o EAN de la unidad ni del pack x6.",
            "Ingredientes, alérgenos y nutrición: etiqueta o ficha técnica específica y vigente.",
            "Certificaciones, beneficios y «sin gluten»: documentación específica; no inferir desde este folleto.",
            "Categoría y subcategoría justificadas, recursos multimedia autorizados y Ecomm ID auténtico por variante.",
        ],
    }


def source(ident):
    pilot = PILOTS[ident]
    return {
        "ecomm_id": ident,
        "sku": "SYNTHETIC-HILERET-" + str(pilot["sale_units"]) + "-NOT-A-LINK",
        "product_name": pilot["name"],
        "variant_description": pilot["presentation"],
        "is_combo": pilot["is_combo"],
        "gtin": None,
        "stock_at_capture": None,
        "captured_at": None,
        "source_kind": "CLIENT_AUXILIARY_REFERENCE",
        "test_id_is_synthetic": True,
        "authentic_ecomm_id": None,
    }


def reference(ident, fields=None):
    pilot, fields = PILOTS[ident], fields or {}

    def contradiction(key, expected):
        value = fields.get(key) or ""
        return value if value.strip().casefold() != expected.casefold() else None

    return {
        "ecomm_id": ident,
        "name": pilot["name"],
        "sku": source(ident)["sku"],
        "presentation": pilot["presentation"],
        "is_combo": pilot["is_combo"],
        "ean": EAN,
        "brand": "Hileret",
        "manufacturer": None,  # no legal manufacturer inferred from a brand/domain
        "hileret_pilot": True,
        "sale_units": pilot["sale_units"],
        "authentic_ecomm_id": None,
        "editorial_presentation": fields.get("presentation") or None,
        "editorial_brand": contradiction("brand", "Hileret") or None,
        "editorial_ean": contradiction("proposed_gtin", EAN) or None,
        "provenance": {
            "name": "Fila del Excel informada por usuario; no catálogo maestro",
            "brand": "Marca declarada; revisión documental pendiente",
            "ean": "EAN declarado compartido; no clave de identidad ni verificación oficial",
            "presentation": "Unidad/pack declarados; caja x9 es logística independiente",
        },
    }


def identity_issues(ref, body):
    """Fail closed on packaging; a unit brochure never establishes a pack x6."""
    issues = []
    identity = body.get("identity", {})
    name = str(identity.get("name") or "").strip().casefold()
    accepted = {ref["name"].casefold()}
    if ref["sale_units"] == 1:
        accepted.add("hileret stevia")
    if name not in accepted:
        issues.append(
            "Nombre/presentación comercial no contrastados: unidad y pack x6 son registros distintos."
        )
    if identity.get("is_combo") is not ref["is_combo"]:
        issues.append(
            "Tipo de venta incompatible o ausente: distinguir unidad, pack x6 y caja logística x9."
        )
    for key, expected in (("editorial_brand", "Hileret"), ("editorial_ean", EAN)):
        if ref.get(key) and ref[key].strip().casefold() != expected.casefold():
            issues.append(
                "La edición local contradice la marca o el EAN declarado; requiere revisión."
            )
    return issues
