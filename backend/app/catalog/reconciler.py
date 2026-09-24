from collections import Counter
from .matcher import CatalogMatcher
from .models import *
from .validator import ProductValidator

class CatalogReconciler:
    def __init__(self, validator: ProductValidator | None = None): self.validator = validator or ProductValidator()
    def reconcile(self, products: list[Product], listings: list[ChannelListing]) -> list[ReconciliationResult]:
        counts = Counter(p.sku for p in products if p.sku)
        matcher = CatalogMatcher(listings)
        results: list[ReconciliationResult] = []
        matched_ids: set[int] = set()
        for product in products:
            issues = self.validator.validate(product, counts)
            matches, method, confidence = matcher.match(product)
            codes = {i.code for i in issues}
            status, reason = self._classification(codes, matches, method)
            if matches:
                matched_ids.update(id(x) for x in matches)
            results.append(ReconciliationResult(product=product, listing=matches[0] if matches else None, status=status, confidence=confidence, reason=reason, match_method=method, matched_identifier=(product.sku if method == MatchMethod.SKU else product.ean if method == MatchMethod.EAN else matches[0].title if matches else None), issues=issues))
        for listing in listings:
            if id(listing) not in matched_ids:
                results.append(ReconciliationResult(listing=listing, status=ReconciliationStatus.UNMATCHED_ML_LISTING, reason="La publicación de Mercado Libre no pudo asociarse claramente.", issues=[]))
        return results
    @staticmethod
    def _classification(codes: set[str], matches: list[ChannelListing], method: MatchMethod) -> tuple[ReconciliationStatus, str]:
        if "SKU_DUPLICATE" in codes or len(matches) > 1:
            return ReconciliationStatus.POSSIBLE_DUPLICATE, "Se encontraron identificadores o publicaciones duplicadas."
        if "SKU_MISSING" in codes or "SKU_INVALID" in codes:
            return ReconciliationStatus.INVALID_SKU, "El SKU está ausente o tiene formato inválido."
        if "EAN_INVALID" in codes:
            return ReconciliationStatus.INVALID_EAN, "El EAN/GTIN tiene formato inválido."
        if any(x in codes for x in {"NAME_MISSING", "PRICE_INVALID", "STOCK_INVALID"}):
            return ReconciliationStatus.INCOMPLETE_DATA, "Faltan datos obligatorios o contienen valores inválidos."
        if method == MatchMethod.TITLE:
            return ReconciliationStatus.REVIEW_REQUIRED, "Coincidencia aproximada por título; requiere confirmación humana."
        if matches:
            return ReconciliationStatus.ALREADY_PUBLISHED, f"Coincidencia exacta por {method.value}."
        return ReconciliationStatus.CANDIDATE_TO_PUBLISH, "No se encontró una publicación asociada."
