"""Conservative brand hints, API Ecomm identity only; ML/TN are evidence sources.

No use of historical ECOMM_APP/ECOMM_APP_RAW inventory to identify variants.
No brand is automatically written or considered verified.
"""
from collections import defaultdict

from sqlalchemy import select

from ..database.models import CatalogSnapshot
from ..integrations.ecomm_app.commercial_audit import _brand_class
from .ecomm_api_product_workspace_service import EcommApiProductWorkspace
from .tiendanube_assisted_match_service import variant_conflict


def _value(value):
    return str(value).strip() if value is not None else ""


def _sku(value):
    return _value(value).casefold()


class EcommApiBrandHints:
    def __init__(self, db):
        self.db = db
        self.workspace = EcommApiProductWorkspace(db)

    def get(self, ecomm_id):
        source = self.workspace.get(ecomm_id)
        api_item = source["source"]
        key = _sku(api_item["sku"])
        if not key or source["source_sku_changed"]:
            raise ValueError("Identidad Ecomm API incompleta o modificada. No se sugieren marcas.")

        owners = defaultdict(set)
        for page in self.workspace._source_pages():
            for parent in page.get("items") or []:
                for variant in parent.get("variants") or []:
                    if variant.get("id") is not None:
                        owners[_sku(variant.get("sku"))].add(_value(variant["id"]))
        if owners[key] != {ecomm_id}:
            return {
                "status": "AMBIGUOUS_API_SKU", "brand": None, "evidence": [],
                "reason": "El SKU aparece en varios IDs Ecomm. No puede asociarse una marca.",
                "external_writes_enabled": False,
            }

        ml = self.db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "MERCADOLIBRE_API"
        ))
        tn = self.db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "TIENDANUBE"
        ))
        evidence = []
        conflicts = []

        tn_rows = [
            row for row in (tn.payload if tn and isinstance(tn.payload, list) else [])
            if isinstance(row, dict) and _sku(row.get("sku")) == key
        ]
        tn_products = {
            _value(row.get("slug") or row.get("name"))
            for row in tn_rows
        }
        if len(tn_products) > 1:
            conflicts.append("Tiendanube usa el mismo SKU para varias fichas.")
        elif tn_rows:
            brands = {
                _value(row.get("brand")) for row in tn_rows
                if _brand_class(row.get("brand")) == "PRESENT"
            }
            if len({b.casefold() for b in brands}) > 1:
                conflicts.append("Tiendanube informa distintas marcas para el mismo SKU.")
            elif len(brands) == 1:
                brand = next(iter(brands))
                evidence.append({
                    "brand": brand, "channel": "TIENDANUBE_CSV",
                    "source_id": _value(tn_rows[0].get("slug")),
                    "title": _value(tn_rows[0].get("name")),
                    "snapshot_at": tn.updated_at.isoformat() if tn else None,
                    "identifier_match": "EXACT_UNIQUE_ECOMM_API_SKU",
                    "verification": "DECLARED_IN_CSV_NOT_MANUFACTURER_VERIFIED",
                })

        for row in (ml.payload if ml and isinstance(ml.payload, list) else []):
            if not isinstance(row, dict):
                continue
            ml_id = _value(row.get("external_id"))
            # Variation records must have their OWN variation SKU.
            listed_sku = (
                _value(row.get("variant_sku"))
                if "#" in ml_id else _value(
                    row.get("variant_sku") or row.get("sku_product")
                    or row.get("sku_effective") or row.get("sku")
                )
            )
            if _sku(listed_sku) != key or _brand_class(row.get("brand")) != "PRESENT":
                continue
            title = _value(row.get("title"))
            if variant_conflict(api_item["product_name"], api_item["sku"], title, listed_sku):
                conflicts.append("Mercado Libre tiene una presentación incompatible con este SKU.")
                continue
            evidence.append({
                "brand": _value(row["brand"]), "channel": "MERCADOLIBRE_API",
                "source_id": ml_id, "title": title,
                "snapshot_at": ml.updated_at.isoformat() if ml else None,
                "identifier_match": "EXACT_UNIQUE_ECOMM_API_SKU",
                "verification": "DECLARED_IN_ML_SNAPSHOT_NOT_MANUFACTURER_VERIFIED",
            })

        brands = {e["brand"].casefold() for e in evidence}
        if len(brands) > 1:
            conflicts.append("Los canales registran marcas distintas para un mismo SKU.")
        return {
            "status": ("CONFLICT" if conflicts else "EVIDENCE_FOUND" if evidence else "NO_EVIDENCE"),
            "brand": evidence[0]["brand"] if evidence and not conflicts else None,
            "ecomm_id": ecomm_id,
            "sku": api_item["sku"],
            "source": "ECOMM_APP_API_STAGE",
            "evidence": evidence[:15],
            "reason": (
                " ".join(sorted(set(conflicts))) if conflicts else
                "La marca aparece declarada en otra fuente. Verificar envase antes de guardar."
                if evidence else
                "No hay una marca declarada con coincidencia de SKU exacta y no ambigua."
            ),
            "external_writes_enabled": False,
        }
