"""Read projections over API variants and existing edits; no new catalogue or decisions."""

from collections import Counter, defaultdict
from .sku_family_service import compare_family_skus
from .ecomm_api_product_workspace_service import _readiness, blank_fields

LABELS = {
    "ean_missing": "EAN no informado en Ecomm-App",
    "ean_repeated": "EAN repetido · revisar presentaciones",
    "sku_repeated": "SKU repetido · no confirma duplicados",
    "possible_duplicates": "Posibles duplicados · revisar códigos",
    "sku_family": "Familias SKU candidatas",
    "barcode_gtin_conflict": "Barcode y GTIN contradictorios",
    "short_description_missing": "Sin descripción corta",
    "long_description_missing": "Sin descripción larga",
    "commercial_title_missing": "Sin título comercial",
    "category_missing": "Sin categoría",
    "subcategory_missing": "Sin subcategoría",
    "attributes_missing": "Sin atributos",
    "images_missing": "Sin imágenes registradas",
    "video_unrecorded": "Sin video · revisar si corresponde",
    "seo_missing": "SEO incompleto",
    "ml_unconfirmed": "Sin publicación confirmada en ML",
    "tn_unconfirmed": "Sin publicación confirmada en TN",
    "proposals_pending": "Propuestas pendientes de revisión",
    "commercial_incomplete": "Ficha comercial incompleta",
    "source_title_short": "Nombre de origen breve (<25 caracteres)",
    "source_variant_short": "Presentación de origen breve (<25 caracteres)",
    "source_title_missing": "Sin nombre en captura Ecomm-App",
    "source_variant_missing": "Sin presentación en captura Ecomm-App",
}


def identity_index(pages):
    rows = [
        v
        for p in pages
        for parent in p.get("items", [])
        for v in parent.get("variants", [])
        if isinstance(v, dict) and not v.get("invalid")
    ]

    def sku(v):
        return str(v.get("sku") or "").strip()

    def gtin(v):
        return str(v.get("gtin") or v.get("barcode") or "").strip()

    codes = Counter(gtin(v) for v in rows)
    owners = Counter(sku(v).casefold() for v in rows)
    groups = defaultdict(set)
    for v in rows:
        s = sku(v)
        if s.isascii() and s.isdigit():
            if len(s) >= 3:
                groups[(3, s[:3])].add(s)
            if len(s) >= 2:
                groups[(2, s[:2])].add(s)
    families = set()
    for (size, _), members in groups.items():
        if len(members) < 2:
            continue
        # The original comparator owns all numerical/special-suffix rules.
        pivots = (
            list(members)[:1]
            if size == 3
            else [
                s
                for s in members
                if len(s) == 5 and compare_family_skus(s, s[:2])["related"]
            ]
        )
        for pivot in pivots[:1]:
            families.update(
                s for s in members if compare_family_skus(pivot, s)["related"]
            )
    return codes, owners, families


def flags(source, edit, index):
    codes, owners, families = index
    started = edit is not None
    fields = (edit.fields or {}) if started else {}
    code = str(source.get("gtin_raw") or source.get("barcode") or "").strip()
    title = str(source.get("product_name") or "").strip()
    variant_description = str(source.get("variant_description") or "").strip()
    sku = str(source.get("sku") or "").strip()
    barcode, gtin = source.get("barcode"), source.get("gtin_raw")
    repeated_code = bool(code and codes[code] > 1)
    repeated_sku = bool(sku and owners[sku.casefold()] > 1)

    def present(key):
        return bool(str(fields.get(key) or "").strip())

    media = fields.get("media") or []
    values = {
        "commercial_incomplete": started and not _readiness({**blank_fields(), **fields})["ready"],
        "ean_missing": not code,
        # These checks concern the captured Ecomm-App source, not the KIKI editor.
        # Under 25 chars is a triage heuristic, never proof of bad copy.
        "source_title_short": bool(title) and len(title) < 25,
        "source_variant_short": bool(variant_description) and len(variant_description) < 25,
        "source_title_missing": not title,
        "source_variant_missing": not variant_description,
        "ean_repeated": repeated_code,
        "sku_repeated": repeated_sku,
        "possible_duplicates": repeated_code or repeated_sku,
        "sku_family": sku in families
        or (repeated_sku and bool(compare_family_skus(sku, sku)["related"])),
        "barcode_gtin_conflict": bool(
            barcode and gtin and str(barcode).strip() != str(gtin).strip()
        ),
        "short_description_missing": started and not present("short_description"),
        "long_description_missing": started and not present("description"),
        "commercial_title_missing": started and not present("title"),
        "category_missing": started and not present("category"),
        "subcategory_missing": started and not present("subcategory"),
        "attributes_missing": started and not bool(fields.get("attributes")),
        "images_missing": started and not any(m.get("kind") == "IMAGE" for m in media),
        "video_unrecorded": started and not any(m.get("kind") == "VIDEO" for m in media),
        "seo_missing": started and not (present("seo_title") and present("seo_description")),
    }
    return [key for key, value in values.items() if value]
