"""Tiendanube vs Ecomm-App: ONLY a completed Ecomm-App Public API capture.

Do not reference, query or fall back to the historical ECOMM_APP XLSX snapshot.
Match a single exact variant SKU to exactly one Ecomm variant identity. SKU
family, GTIN, product title and parent code are NOT substitute identities.
"""
from collections import Counter

from ..integrations.ecomm_app.catalog_stage import STAGE_SOURCE, stage_status
from ..repositories.catalog_repository import CatalogRepository


class TiendanubeApiCatalogService:
    def __init__(self, db):
        self.repo = CatalogRepository(db)

    def report(self):
        tn_record = self.repo.snapshot_record("TIENDANUBE")
        tn = tn_record.payload if tn_record else []
        api_record = self.repo.snapshot_record(STAGE_SOURCE)
        pages = api_record.payload if api_record else []
        status = stage_status(pages)
        base = {
            "ecomm_source": STAGE_SOURCE,
            "ecomm_captured_at": pages[-1].get("captured_at") if pages else None,
            "tiendanube_source": "TIENDANUBE_CSV",
            "tiendanube_snapshot_at": (
                tn_record.updated_at.isoformat() if tn_record else None
            ),
            "mode": "ECOMM_API_CAPTURE_ONLY",
            "external_writes_enabled": False,
        }
        if not tn:
            return {
                **base, "available": False, "summary": {}, "items": [],
                "warning": "Primero importá el CSV de Tiendanube. Ecomm-App continúa exclusivamente por API.",
            }
        if not status["complete"]:
            return {
                **base, "available": False, "summary": {}, "items": [],
                "warning": (
                    "La captura Ecomm-App por API no está completa. "
                    "No se utiliza el Excel anterior como alternativa."
                ),
            }

        sku_index = {}
        valid_variants = 0
        for page in pages:
            for parent in page.get("items") or []:
                if not isinstance(parent, dict):
                    continue
                for variant in parent.get("variants") or []:
                    if not isinstance(variant, dict) or variant.get("invalid"):
                        continue
                    valid_variants += 1
                    sku = variant.get("sku")
                    vid = variant.get("id")
                    if not isinstance(sku, str) or not sku.strip() or vid is None or str(vid) == "":
                        continue
                    key = sku.strip().casefold()
                    sku_index.setdefault(key, []).append({
                        "ecomm_id": str(vid),
                        "sku": sku.strip(),
                        "stock": variant.get("total_stock"),
                        "is_combo": variant.get("is_combo") is True or parent.get("is_combo") is True,
                    })

        counts_tn = Counter(str(row.get("sku") or "").strip().casefold() for row in tn
                            if str(row.get("sku") or "").strip())
        results = []
        for row in tn:
            sku = str(row.get("sku") or "").strip()
            matches = sku_index.get(sku.casefold(), []) if sku else []
            # Duplicate API variants are ambiguous even if they claim same ID.
            unique_id = len(matches) == 1 and len({
                m["ecomm_id"] for m in matches
            }) == 1
            status_name = (
                "SKU_MISSING" if not sku else
                "SKU_DUPLICATE_TN" if counts_tn[sku.casefold()] > 1 else
                "SKU_AMBIGUOUS_ECOMM" if len(matches) > 1 else
                "MATCHED_SKU" if unique_id else
                "UNMATCHED_SKU"
            )
            match = matches[0] if status_name == "MATCHED_SKU" else None
            results.append({
                **row,
                "status": status_name,
                "matched_ecomm_id": match["ecomm_id"] if match else None,
                "ecomm_stock_at_capture": match["stock"] if match else None,
                "ecomm_is_combo": match["is_combo"] if match else None,
            })
        counts = Counter(item["status"] for item in results)
        return {
            **base, "available": True,
            "summary": {
                "rows": len(tn),
                "products": len({row.get("slug") for row in tn if row.get("slug")}),
                "ecomm_products": valid_variants,
                **{key: counts[key] for key in (
                    "MATCHED_SKU", "UNMATCHED_SKU", "SKU_DUPLICATE_TN",
                    "SKU_AMBIGUOUS_ECOMM", "SKU_MISSING",
                )},
            },
            "items": results,
            "warning": (
                "Las coincidencias son candidatos por SKU único exacto, no verifican "
                "presentación, marca, composición de packs ni precio. "
                "Ecomm-App corresponde a una captura API, NO stock en vivo."
            ),
            "policy": (
                "Ecomm-App exclusivamente ECOMM_APP_API_STAGE; Tiendanube CSV. "
                "Nunca se carga ni consulta ECOMM_APP XLSX histórico. "
                "SKU exacto y único no confirma identidad comercial. Solo lectura."
            ),
        }
