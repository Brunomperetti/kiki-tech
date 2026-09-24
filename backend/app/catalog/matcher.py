from collections import defaultdict
from difflib import SequenceMatcher
from .models import ChannelListing, MatchMethod, Product
from .normalizer import normalize_title

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
            if value: result[value].append(item)
        return result
    def match(self, product: Product) -> tuple[list[ChannelListing], MatchMethod, float]:
        if product.sku and product.sku in self.by_sku:
            return self.by_sku[product.sku], MatchMethod.SKU, 1.0
        if product.ean and product.ean in self.by_ean:
            return self.by_ean[product.ean], MatchMethod.EAN, 0.98
        title = normalize_title(product.name)
        if title:
            scored = [(SequenceMatcher(None, title, normalize_title(x.title) or "").ratio(), x) for x in self.listings]
            candidates = [x for score, x in scored if score >= self.title_threshold]
            if candidates:
                return candidates, MatchMethod.TITLE, max(score for score, _ in scored)
        return [], MatchMethod.NONE, 0.0
