"""Deterministic, read-only documentary cohorts from the current Ecomm API audit.

Brand phrases are only literal search hints in the product title, never a
verified manufacturer, source URL, EAN identity or authorization to fetch.
No API calls, AI, approvals, channel writes or database mutations.
"""
from collections import defaultdict
import csv
from hashlib import sha256
from io import StringIO
import json
import re
import unicodedata

from .contractual_delivery_audit_service import build_delivery_audit
from .research_manifest_service import _cell

MAX_COHORT = 20
MAX_CATALOG = 10000
# Explicit textual hypotheses taken from the already reviewed pilot planning.
# Adding a new phrase requires a code review: none is auto-discovered as fact.
BRAND_PHRASES = (
    "Natural Seed", "Saint Gottard", "Dimax", "Vitamin Way", "Sri Sri",
    "Yin Yang", "Natier", "Granix", "Geonat", "El Castillo", "Graal",
    "Natufarma", "Hileret", "Laur", "Juan Valdez", "Prama",
)


def _tokens(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    plain = "".join(c for c in text if not unicodedata.combining(c))
    return " " + re.sub(r"[^a-z0-9]+", " ", plain.casefold()).strip() + " "


def _brand_mentions(name):
    words = _tokens(name)
    return [phrase for phrase in BRAND_PHRASES if _tokens(phrase) in words]


def _suspicious_pack(name, presentation):
    # Never assume a numeric presentation alone (e.g. x 30 tablets) is a pack.
    text = _tokens(f"{name} {presentation}")
    return any(f" {label} " in text for label in ("pack", "multipack", "combo", "bundle"))


def plan_cohorts_from_audit(summary, rows):
    """Build reviewable 1–20 item cohorts. Never mark sources or brands valid."""
    if (
        not isinstance(rows, list) or len(rows) > MAX_CATALOG
        or len(rows) != summary.get("total")
        or len({r.get("ecomm_id") for r in rows}) != len(rows)
        or summary.get("classified_variants") != len(rows)
    ):
        raise ValueError("Auditoría de la captura incompleta o con variantes repetidas.")

    normalized = sorted(
        (str(row.get("ecomm_id") or ""), str(row.get("sku") or ""),
         str(row.get("name") or ""), str(row.get("presentation") or ""),
         str(row.get("api_barcode") or ""), str(row.get("captured_at") or ""))
        for row in rows
    )
    signature = sha256(
        json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()

    matched = defaultdict(list)
    eligible = 0
    unattributed = 0
    ambiguous = 0
    pack_suspected = 0
    excluded_by_barcode = 0
    for row in rows:
        if row.get("quality_stage") != "FIND_ORIGINAL":
            continue
        if "BARCODE_RESEARCH_NOT_ELIGIBLE" in row.get("gaps", []):
            excluded_by_barcode += 1
            continue
        if not all(row.get(field) for field in ("ecomm_id", "sku", "name", "presentation", "api_barcode")):
            # No conjectural identity may enter a documentary cohort.
            excluded_by_barcode += 1
            continue
        eligible += 1
        if _suspicious_pack(row["name"], row["presentation"]):
            pack_suspected += 1
            continue
        mentions = _brand_mentions(row["name"])
        if len(mentions) == 0:
            unattributed += 1
            continue
        if len(mentions) > 1:
            ambiguous += 1
            continue
        matched[mentions[0]].append(row)

    cohorts = []
    for label in BRAND_PHRASES:
        group = sorted(
            matched[label], key=lambda r: (str(r["sku"]).casefold(), str(r["ecomm_id"]))
        )
        for start in range(0, len(group), MAX_COHORT):
            part = group[start:start + MAX_COHORT]
            cohorts.append({
                "id": f"P{len(cohorts)+1:03d}",
                "brand_phrase": label,
                "brand_verified": False,
                "manufacturer_verified": False,
                "source_urls_verified": 0,
                "count": len(part),
                "items": [
                    {
                        "ecomm_id": str(row["ecomm_id"]),
                        "sku": str(row["sku"]),
                        "name": row["name"],
                        "presentation": row["presentation"],
                        "gtin_lookup_hint": str(row["api_barcode"]),
                        "captured_at": row["captured_at"],
                        "source_url": None,
                        "next_step": "REVISAR_FABRICANTE_Y_URL_OFICIAL",
                    }
                    for row in part
                ],
            })
    grouped = sum(group["count"] for group in cohorts)
    if eligible != grouped + unattributed + ambiguous + pack_suspected:
        raise ValueError("La clasificación de cohortes perdió variantes.")
    if len({item["ecomm_id"] for group in cohorts for item in group["items"]}) != grouped:
        raise ValueError("Una variante aparece en más de un lote.")
    return {
        "mode": "READ_ONLY_DOCUMENTARY_COHORTS",
        "source": "ECOMM_APP_API_STAGE",
        "capture_fingerprint": signature,
        "total_variants": len(rows),
        "eligible_to_look_up": eligible,
        "grouped_variants": grouped,
        "cohort_count": len(cohorts),
        "unattributed": unattributed,
        "ambiguous_brand_mentions": ambiguous,
        "pack_text_suspects": pack_suspected,
        "barcode_not_eligible_for_research": excluded_by_barcode,
        "other_quality_stages": len(rows) - eligible - excluded_by_barcode,
        "max_per_cohort": MAX_COHORT,
        "network_requests": 0,
        "ai_requests": 0,
        "db_writes": 0,
        "external_writes_enabled": False,
        "can_auto_fetch": False,
        "brand_hints_verified": False,
        "cohorts": cohorts,
        "policy": (
            "Las menciones de marca son pistas textuales del nombre Ecomm; "
            "no prueban fabricante, EAN, derechos ni URL. "
            "La captura puede cambiar: comparar huella e identidad antes de crear "
            "cualquier manifiesto o consultar una fuente."
        ),
    }


def build_documentary_cohorts(db):
    summary, rows = build_delivery_audit(db)
    return plan_cohorts_from_audit(summary, rows)


def export_documentary_cohorts_csv(plan):
    out = StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow((
        "lote", "mencion_de_marca_no_verificada", "ecomm_id", "sku",
        "nombre_api", "presentacion_api", "gtin_api_solo_busqueda",
        "capturado", "huella_captura", "fabricante_validado",
        "url_oficial_validada", "proxima_accion",
    ))
    for cohort in plan["cohorts"]:
        for item in cohort["items"]:
            writer.writerow([
                _cell(value) for value in (
                    cohort["id"], cohort["brand_phrase"],
                    item["ecomm_id"], item["sku"], item["name"],
                    item["presentation"], item["gtin_lookup_hint"],
                    item["captured_at"], plan["capture_fingerprint"],
                    "NO", "NO", item["next_step"],
                )
            ])
    return "\ufeff" + out.getvalue()
