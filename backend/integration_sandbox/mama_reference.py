"""User-supplied identification, NOT an API capture or manufacturer document."""

from decimal import Decimal, InvalidOperation

PILOT_ID = "PILOT-MAMA-350-SYNTHETIC"
NAME = "Fideos De Arroz Mama 10mm 350g"
CATALOG_NAME = "Mama Rice Noodles 350g (10 Mm.)"
URL = (
    "https://www.mama.co.th/en/products-export-brand-list/21/34/Instant-Rice-Vermicelli"
)
EAN = "8851876201433"
SKU_MARKER = "SYNTHETIC-LOCAL-PILOT-NOT-A-SKU-LINK"
SOURCE_EVENT = "MAMA_PILOT_REFERENCE_REGISTERED"


def references():
    return {
        "test_id": PILOT_ID,
        "test_id_is_synthetic": True,
        "authentic_ecomm_id": None,
        "binding_status": "PENDING",
        "network_enabled": False,
        "excel": {
            "file_name": "productos.xlsx",
            "row": 37,
            "availability": "USER_TRANSCRIPTION_ONLY",
            "original_file_available": False,
            "original_file_sha256": None,
            "source": "Mensaje del usuario de etapa 2J; archivo no suministrado al entorno",
            "name": NAME,
            "brand": "Mama",
            "declared_ean": EAN,
            "ean_checksum_valid": sum(
                int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(EAN)
            )
            % 10
            == 0,
            "ean_official_correspondence_verified": False,
            "file_sku": "fideos 10mm Mama",
            "declared_presentation": "350 g",
            "declared_width": "10 mm",
            "logistic_weight": "0,4 kg",
            "logistic_weight_is_net_content": False,
            "description": "",
            "seo_title": "",
            "seo_description": "",
        },
        "manufacturer_candidate": {
            "manufacturer": "Thai President Foods",
            "url": URL,
            "catalog_item_reported": CATALOG_NAME,
            "source": "Referencia candidata suministrada por el usuario; sin consulta del sistema",
            "downloaded": False,
            "consulted_at": None,
            "document_sha256": None,
            "provenance_reviewed": False,
            "ean_confirmed": False,
        },
        "missing_evidence": [
            "Copia auténtica de etiqueta o ficha técnica del fabricante, con original y procedencia revisable.",
            "Correspondencia explícita del EAN 8851876201433 con Mama, ancho 10 mm y contenido neto 350 g.",
            "Fabricante y tipo de venta (unidad o pack) documentados; no inferir contenido neto del peso logístico.",
            "Ingredientes, alérgenos, nutrientes y cualquier certificación: documentación específica por afirmación.",
            "Categoría y subcategoría: evidencia y clasificación justificada; no asignarlas automáticamente.",
            "Ecomm ID auténtico, validado en una referencia autorizada del catálogo maestro.",
        ],
    }


def source():
    return {
        "ecomm_id": PILOT_ID,
        "sku": SKU_MARKER,
        "product_name": NAME,
        "variant_description": "350 g",
        "is_combo": None,
        "gtin": None,
        "stock_at_capture": None,
        "captured_at": None,
        "source_kind": "CLIENT_AUXILIARY_REFERENCE",
        "test_id_is_synthetic": True,
        "authentic_ecomm_id": None,
    }


def reference(fields=None):
    fields = fields or {}
    return {
        "ecomm_id": PILOT_ID,
        "name": NAME,
        "sku": SKU_MARKER,
        "presentation": "350 g",
        "is_combo": None,
        "ean": EAN,
        "brand": "Mama",
        "manufacturer": "Thai President Foods",
        "width": "10 mm",
        "commercial_pilot": True,
        "authentic_ecomm_id": None,
        "editorial_presentation": fields.get("presentation") or None,
        "editorial_brand": fields.get("brand") or None,
        "editorial_ean": fields.get("proposed_gtin") or None,
        "editorial_manufacturer": fields.get("manufacturer") or None,
        "provenance": {
            "name": "Excel fila 37 informado por usuario; no lectura del archivo",
            "ean": "Declarado por cliente; checksum válido, correspondencia oficial pendiente",
            "brand": "Marca declarada por cliente",
            "manufacturer": "Fabricante candidato informado; sin documento específico",
            "presentation": "350 g y 10 mm declarados; 0,4 kg es peso logístico",
        },
    }


def identity_issues(ref, body):
    issues = []
    name = str(body.get("identity", {}).get("name") or "").casefold().strip()
    if name not in {NAME.casefold(), CATALOG_NAME.casefold()}:
        issues.append(
            "Nombre no corresponde a las dos referencias declaradas del piloto; requiere contraste humano."
        )
    if body.get("identity", {}).get("is_combo") is None:
        issues.append("Tipo de venta sin evidencia explícita de unidad/pack.")
    for field, expected, label, unit in [
        ("width", Decimal(10), "Ancho 10 mm", "mm"),
        ("net_weight", Decimal(350), "Contenido neto 350 g", "g"),
    ]:
        claim = next((c for c in body.get("claims", []) if c["field"] == field), None)
        try:
            quantity = Decimal(claim["value"].replace(",", ".")) if claim else None
            actual_unit = (claim.get("unit") or "").casefold().strip() if claim else ""
            if field == "net_weight" and actual_unit == "kg":
                quantity *= 1000
                actual_unit = "g"
            if quantity != expected or actual_unit != unit:
                raise ValueError
        except (ValueError, InvalidOperation, TypeError):
            issues.append(
                f"{label}: falta respaldo explícito compatible. El peso logístico no sirve como contenido neto."
            )
    for key, expected in [
        ("editorial_brand", "Mama"),
        ("editorial_ean", EAN),
        ("editorial_manufacturer", "Thai President Foods"),
    ]:
        if ref.get(key) and ref[key].strip().casefold() != expected.casefold():
            issues.append(
                "La edición local contradice la referencia declarada de marca, EAN o fabricante."
            )
    return issues
