"""Read-only 20-item GTIN research pilot with bounded external probes.

No publication changes, decisions, database writes or automatic validations.
"""
from .enrichment_review_service import EnrichmentReviewService
from .enrichment_service import EnrichmentService
from .gtin_candidate_service import GtinCandidateService
from .external_gtin_candidate_service import ExternalGtinCandidateService


class GtinBatchPilotService:
    LIMIT = 20
    EXTERNAL_LIMIT = 5  # Bounded to avoid a long synchronous request / source throttling.

    def __init__(self, db):
        self.review = EnrichmentReviewService(db)
        self.internal = GtinCandidateService(db)
        self.external = ExternalGtinCandidateService(db)

    def run(self, product_keys: list[str]) -> dict:
        keys = [str(k).strip() for k in product_keys or []]
        if not keys or len(keys) > self.LIMIT or not all(keys) or len(keys) != len(set(keys)):
            raise ValueError("Seleccioná entre 1 y 20 productos diferentes.")
        report = self.review.readiness.report()
        current = {
            self.review.product_key(row["product"]): row["product"]
            for row in report.get("items") or [] if row.get("product")
        }
        if any(key not in current or current[key].get("ean") for key in keys):
            raise ValueError("La selección incluye productos inexistentes o con EAN.")
        # Prioritize identifiable packaged products; omit likely bulk/fractioned
        # products from external lookup until exact manufacturer data is supplied.
        def priority(key):
            p = current[key]
            title = EnrichmentService._normalize(p.get("name"))
            bulk = any(word in title for word in ("SUELTO", "SUELTA", "GRANEL", "FRACCIONADO", "FRACCIONADA"))
            known_brand = bool(p.get("brand"))
            tokens = len(EnrichmentService._informative_tokens(p.get("name")))
            return (bulk, not known_brand, -tokens, key)

        keys.sort(key=priority)
        items = []
        counts = {"candidate": 0, "no_candidate": 0, "source_unavailable": 0, "needs_product_data": 0, "external_not_checked": 0}
        external_used = 0
        for key in keys:
            product = current[key]
            internal_result = self.internal.candidates(key)
            external_result = None
            title = EnrichmentService._normalize(product.get("name"))
            bulk = any(word in title for word in ("SUELTO", "SUELTA", "GRANEL", "FRACCIONADO", "FRACCIONADA"))
            if not internal_result.get("candidates") and not bulk and external_used < self.EXTERNAL_LIMIT:
                external_used += 1
                external_result = self.external.lookup(key)
            elif not internal_result.get("candidates"):
                counts["external_not_checked"] += 1
            candidates = internal_result.get("candidates") or (external_result or {}).get("candidates") or []
            if candidates:
                status = "candidate"
            elif external_result and external_result.get("unavailable"):
                status = "source_unavailable"
            elif external_result and "suficientemente específica" in external_result.get("message", ""):
                status = "needs_product_data"
            elif external_result is None:
                status = "external_not_checked"
            else:
                status = "no_candidate"
            if status != "external_not_checked":
                counts[status] += 1
            items.append({
                "product_key": key, "product_name": product.get("name"), "sku": product.get("sku"),
                "status": status, "candidates": candidates,
                "internal_message": internal_result.get("message"),
                "external_message": (external_result or {}).get("message") if external_result else "Fuente externa no consultada en este piloto.",
                "external_checked": external_result is not None,
                "selection_reason": "Posible producto suelto/fraccionado; requiere verificar si tiene GTIN propio." if bulk else "Producto priorizado según marca y descripción disponible.",
            })
        return {
            "requested": len(keys), "external_checked": sum(bool(i["external_checked"]) for i in items),
            "external_limit": self.EXTERNAL_LIMIT, "summary": counts,
            "items": items,
            "policy": "Solo sugerencias; revisar fabricante y presentación. No se modificaron datos.",
        }
