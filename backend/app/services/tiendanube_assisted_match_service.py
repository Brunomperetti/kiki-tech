"""Conservative, read-only candidate discovery for Tiendanube SKU mismatches."""
import re
import unicodedata
from difflib import SequenceMatcher

from .tiendanube_csv_service import TiendanubeCsvService


def normalize(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def numbers(value):
    return set(re.findall(r"\d+(?:[.,]\d+)?", normalize(value)))


class TiendanubeAssistedMatchService:
    def __init__(self, db):
        self.catalog = TiendanubeCsvService(db)

    def report(self):
        existing = self.catalog.report()
        if not existing["available"]:
            return {"available": False, "items": [], "summary": {}}
        ecomm = self.catalog.repo.snapshot("ECOMM_APP")
        candidates = []
        for item in existing["items"]:
            if item["status"] != "UNMATCHED_SKU":
                continue
            source_name = normalize(item["name"])
            source_brand = normalize(item["brand"])
            if not source_name or len(source_name) < 9:
                continue
            proposed = []
            for target in ecomm:
                target_name = normalize(target.get("name"))
                if not target_name:
                    continue
                target_brand = normalize(target.get("brand"))
                if source_brand and target_brand and source_brand != target_brand:
                    continue
                # Different quantities/packs never become a high-confidence match.
                if numbers(item["name"]) != numbers(target.get("name")):
                    continue
                score = SequenceMatcher(None, source_name, target_name).ratio()
                if score < 0.85:
                    continue
                proposed.append({
                    "ecomm_id": str(target.get("ecomm_id") or ""),
                    "sku": str(target.get("sku_effective") or target.get("sku") or ""),
                    "name": target.get("name") or "",
                    "brand": target.get("brand") or "",
                    "similarity": round(score, 3),
                    "confidence": "HIGH" if score >= 0.96 and source_brand and target_brand == source_brand else "MEDIUM",
                    "evidence": "Similitud de nombre; marca compatible; números de presentación coincidentes. Requiere verificación humana.",
                })
            proposed.sort(key=lambda x: (-x["similarity"], x["ecomm_id"]))
            candidates.append({
                "tiendanube_sku": item["sku"],
                "tiendanube_name": item["name"],
                "tiendanube_brand": item["brand"],
                "tiendanube_slug": item["slug"],
                "candidates": proposed[:3],
                "status": "REVIEW_REQUIRED" if proposed else "NO_SAFE_CANDIDATE",
            })
        return {
            "available": True,
            "summary": {
                "sku_unmatched": existing["summary"].get("UNMATCHED_SKU", 0),
                "with_proposals": sum(bool(x["candidates"]) for x in candidates),
                "without_proposals": sum(not x["candidates"] for x in candidates),
            },
            "items": candidates,
            "policy": "Propuestas internas para revisión, sin vinculación ni publicación automática. No se infiere EAN.",
        }
