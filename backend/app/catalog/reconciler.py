from collections import Counter

from .matcher import CatalogMatcher
from .models import (
    ChannelListing,
    MatchMethod,
    Product,
    ReconciliationResult,
    ReconciliationStatus,
)
from .validator import ProductValidator


class CatalogReconciler:
    def __init__(self, validator: ProductValidator | None = None):
        self.validator = validator or ProductValidator()

    def reconcile(
        self, products: list[Product], listings: list[ChannelListing]
    ) -> list[ReconciliationResult]:
        counts = Counter(
            identifier
            for product in products
            for identifier in set(
                product.sku_aliases or ([product.sku] if product.sku else [])
            )
        )
        matcher = CatalogMatcher(listings)
        results: list[ReconciliationResult] = []
        matched_ids: set[int] = set()
        for product in products:
            issues = self.validator.validate(product, counts)
            match = matcher.match(product)
            codes = {issue.code for issue in issues}
            status, reason = self._classification(
                codes, match.listings, match.method, match.alias_ambiguity
            )
            matched_ids.update(id(item) for item in match.listings)
            results.append(
                ReconciliationResult(
                    product=product,
                    listing=match.listings[0] if match.listings else None,
                    status=status,
                    confidence=match.confidence,
                    reason=reason,
                    match_method=match.method,
                    matched_identifier=match.matched_identifier,
                    issues=issues,
                )
            )
        for listing in listings:
            if id(listing) not in matched_ids:
                results.append(
                    ReconciliationResult(
                        listing=listing,
                        status=ReconciliationStatus.UNMATCHED_ML_LISTING,
                        reason="La publicación de Mercado Libre no pudo asociarse claramente.",
                        issues=[],
                    )
                )
        return results

    @staticmethod
    def _classification(
        codes: set[str],
        matches: list[ChannelListing],
        method: MatchMethod,
        alias_ambiguity: bool = False,
    ) -> tuple[ReconciliationStatus, str]:
        if alias_ambiguity:
            return (
                ReconciliationStatus.REVIEW_REQUIRED,
                "Distintos aliases del producto coinciden con publicaciones diferentes; requiere revisión.",
            )
        if "SKU_DUPLICATE" in codes or len(matches) > 1:
            return (
                ReconciliationStatus.POSSIBLE_DUPLICATE,
                "Se encontraron identificadores o publicaciones duplicadas.",
            )
        if "SKU_MISSING" in codes or "SKU_INVALID" in codes:
            return (
                ReconciliationStatus.INVALID_SKU,
                "El SKU está ausente o tiene formato inválido.",
            )
        if "EAN_INVALID" in codes:
            return (
                ReconciliationStatus.INVALID_EAN,
                "El EAN/GTIN tiene formato inválido.",
            )
        if any(
            code in codes for code in {"NAME_MISSING", "PRICE_INVALID", "STOCK_INVALID"}
        ):
            return (
                ReconciliationStatus.INCOMPLETE_DATA,
                "Faltan datos obligatorios o contienen valores inválidos.",
            )
        if method == MatchMethod.TITLE:
            return (
                ReconciliationStatus.REVIEW_REQUIRED,
                "Coincidencia aproximada por título; requiere confirmación humana.",
            )
        if matches:
            return (
                ReconciliationStatus.ALREADY_PUBLISHED,
                f"Coincidencia exacta por {method.value}.",
            )
        return (
            ReconciliationStatus.CANDIDATE_TO_PUBLISH,
            "No se encontró una publicación asociada.",
        )
