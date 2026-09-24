from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
import re

from .models import ChannelListing, MatchMethod, Product
from .normalizer import normalize_title


@dataclass
class MatchResult:
    listings: list[ChannelListing]
    method: MatchMethod
    confidence: float
    matched_identifier: str | None = None
    alias_ambiguity: bool = False


class CatalogMatcher:
    def __init__(self, listings: list[ChannelListing], title_threshold: float = 0.86):
        self.listings = listings
        self.by_sku = self._index("sku")
        self.by_ean = self._index("ean")
        self.title_threshold = title_threshold

    def _index(self, field: str) -> dict[str, list[ChannelListing]]:
        result: dict[str, list[ChannelListing]] = defaultdict(list)
        for item in self.listings:
            value = getattr(item, field)
            if value:
                result[value].append(item)
        return result

    @staticmethod
    def _identifiers(primary: str | None, aliases: list[str]) -> list[str]:
        return list(dict.fromkeys(value for value in [primary, *aliases] if value))

    @staticmethod
    def _identifier_match(
        identifiers: list[str],
        index: dict[str, list[ChannelListing]],
        method: MatchMethod,
        confidence: float,
    ) -> MatchResult | None:
        evidence = {
            identifier: index[identifier]
            for identifier in identifiers
            if identifier in index
        }
        if not evidence:
            return None
        listings = list(
            {
                id(listing): listing for group in evidence.values() for listing in group
            }.values()
        )
        return MatchResult(
            listings=listings,
            method=method,
            confidence=confidence,
            matched_identifier=", ".join(evidence),
            # Different aliases pointing to different listings are conflicting
            # evidence. Repeated listings for one identifier remain duplicates.
            alias_ambiguity=len(evidence) > 1 and len(listings) > 1,
        )

    def match(self, product: Product) -> MatchResult:
        sku_match = self._identifier_match(
            [
                sku
                for sku in self._identifiers(product.sku, product.sku_aliases)
                if re.fullmatch(r"[A-Z0-9._/-]+", sku)
            ],
            self.by_sku,
            MatchMethod.SKU,
            1.0,
        )
        if sku_match:
            return sku_match
        ean_match = self._identifier_match(
            [
                ean
                for ean in self._identifiers(product.ean, product.ean_aliases)
                if ean.isdigit() and len(ean) in {8, 12, 13, 14}
            ],
            self.by_ean,
            MatchMethod.EAN,
            0.98,
        )
        if ean_match:
            return ean_match

        title = normalize_title(product.name)
        if title:
            scored = [
                (
                    SequenceMatcher(
                        None, title, normalize_title(item.title) or ""
                    ).ratio(),
                    item,
                )
                for item in self.listings
            ]
            candidates = [
                item for score, item in scored if score >= self.title_threshold
            ]
            if candidates:
                return MatchResult(
                    candidates,
                    MatchMethod.TITLE,
                    max(score for score, _ in scored),
                    candidates[0].title,
                )
        return MatchResult([], MatchMethod.NONE, 0.0)
