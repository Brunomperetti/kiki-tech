"""Conservative read-only GTIN candidates from the current KIKI catalog.

A checksum-valid GTIN is NOT evidence of ownership or a verified external source.
Candidates are never saved or accepted automatically.
"""
from collections import defaultdict

from .enrichment_review_service import EnrichmentReviewService
from .enrichment_external_research_service import EnrichmentExternalResearchService
from .enrichment_service import EnrichmentService


class GtinCandidateService:
    def __init__(self, db):
        self.review = EnrichmentReviewService(db)

    def candidates(self, product_key: str) -> dict:
        report = self.review.readiness.report()
        rows = report.get("items") or []
        target = next(
            (row for row in rows
             if row.get("product") and self.review.product_key(row["product"]) == product_key),
            None,
        )
        if target is None:
            raise ValueError("Producto no encontrado en el catálogo actual.")
        product = target["product"]
        if product.get("ean"):
            return {"product_key": product_key, "candidates": [], "message": "El producto ya tiene EAN."}

        title = EnrichmentService._normalize(product.get("name"))
        # Exact titles only: do not infer codes across flavors, sizes or multipacks.
        if not title or len(EnrichmentService._informative_tokens(product.get("name"))) < 2:
            return {"product_key": product_key, "candidates": [], "message": "El título no identifica una presentación exacta."}

        by_gtin = defaultdict(list)
        for row in rows:
            other = row.get("product") or {}
            if self.review.product_key(other) == product_key:
                continue
            ean = str(other.get("ean") or "").strip()
            if not EnrichmentExternalResearchService._valid_gtin(ean):
                continue
            if EnrichmentService._normalize(other.get("name")) != title:
                continue
            if product.get("brand") and other.get("brand") and (
                EnrichmentService._normalize(product["brand"])
                != EnrichmentService._normalize(other["brand"])
            ):
                continue
            by_gtin[ean].append(other)

        # Conflicting GTINs for the same title are unsafe to propose.
        if len(by_gtin) > 1:
            return {"product_key": product_key, "candidates": [],
                    "message": "Hay códigos diferentes para el mismo título; requiere investigación manual."}
        candidates = []
        for ean, matching in by_gtin.items():
            source = matching[0]
            candidates.append({
                "ean": ean,
                "matched_name": source.get("name"),
                "matched_sku": source.get("sku") or source.get("sku_effective"),
                "matched_brand": source.get("brand"),
                "match_type": "EXACT_CATALOG_TITLE",
                "confidence": "CANDIDATE_ONLY",
                "reason": "Mismo título normalizado y dígito verificador válido en otro producto de KIKI. No es una verificación del fabricante.",
            })
        return {
            "product_key": product_key,
            "candidates": candidates,
            "message": "Revisá la marca, presentación y fuente oficial antes de aceptar." if candidates else "KIKI no encontró un GTIN comparable en el catálogo interno.",
        }
