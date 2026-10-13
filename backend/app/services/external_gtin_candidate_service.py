"""Opt-in, read-only lookup of barcode candidates from Open Food Facts.

Open Food Facts is community-contributed, not manufacturer certification.
Never accept a barcode automatically. Network requests use a fixed HTTPS host.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher

from .enrichment_review_service import EnrichmentReviewService
from .enrichment_external_research_service import EnrichmentExternalResearchService
from .enrichment_service import EnrichmentService


class ExternalGtinCandidateService:
    API = "https://world.openfoodfacts.org/cgi/search.pl"
    def __init__(self, db):
        self.review = EnrichmentReviewService(db)

    def lookup(self, product_key: str) -> dict:
        rows = self.review.readiness.report().get("items") or []
        target = next((row.get("product") for row in rows
            if row.get("product") and self.review.product_key(row["product"]) == product_key), None)
        if target is None:
            raise ValueError("El producto ya no está disponible.")
        if target.get("ean"):
            return {"candidates": [], "message": "Este producto ya tiene EAN.", "source": "Open Food Facts"}
        title = str(target.get("name") or "").strip()
        normalized = EnrichmentService._normalize(title)
        if len(normalized) < 8 or len(EnrichmentService._informative_tokens(title)) < 2:
            return {"candidates": [], "message": "Falta una descripción suficientemente específica para buscar.", "source": "Open Food Facts"}
        terms = " ".join(title.split()[:8])
        query = urllib.parse.urlencode({
            "search_terms": terms, "search_simple": 1, "action": "process",
            "json": 1, "page_size": 15, "fields": "code,product_name,brands,quantity",
        })
        request = urllib.request.Request(self.API + "?" + query, headers={
            "User-Agent": "KikiTechCatalogResearch/1.0 (https://github.com/Brunomperetti/kiki-tech)",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(request, timeout=6) as response:
                data = json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            return {"candidates": [], "message": "La fuente externa no respondió. Probá más tarde.", "source": "Open Food Facts", "unavailable": True}

        candidates = []
        seen = set()
        brand = EnrichmentService._normalize(target.get("brand"))
        for entry in (data.get("products") or [])[:15]:
            code = str(entry.get("code") or "").strip()
            name = str(entry.get("product_name") or "").strip()
            external_brand = str(entry.get("brands") or "").strip()
            if not EnrichmentExternalResearchService._valid_gtin(code) or code in seen or not name:
                continue
            normalized_name = EnrichmentService._normalize(name)
            similarity = SequenceMatcher(None, normalized, normalized_name).ratio()
            # Do not compare a 500 g / 1 kg pack or altered flavor as equivalent.
            product_numbers = set(re.findall(r"\d+", normalized))
            candidate_numbers = set(re.findall(r"\d+", normalized_name + " " + EnrichmentService._normalize(entry.get("quantity"))))
            if product_numbers != candidate_numbers:
                continue
            if brand and brand not in EnrichmentService._normalize(external_brand):
                continue
            if similarity < 0.91:
                continue
            seen.add(code)
            candidates.append({
                "ean": code, "matched_name": name, "matched_brand": external_brand,
                "quantity": entry.get("quantity") or "",
                "source_name": "Open Food Facts (base colaborativa)",
                "source_url": "https://world.openfoodfacts.org/product/" + code,
                "confidence": "REQUIRES_REVIEW",
                "similarity": round(similarity, 3),
                "reason": "Coincidencia textual alta en base colaborativa; verificar marca, sabor, tamaño, pack y fuente oficial.",
            })
        return {
            "candidates": candidates[:5], "source": "Open Food Facts",
            "message": ("Candidatos externos para comprobar; ninguno está verificado automáticamente."
                if candidates else "No se encontraron candidatos externos suficientemente precisos. No significa que el producto no tenga GTIN."),
        }
