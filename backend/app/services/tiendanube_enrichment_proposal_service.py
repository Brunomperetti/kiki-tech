"""Evidence-only commercial copy proposals; no LLM or external updates."""
from collections import Counter
import re
import unicodedata
from .tiendanube_csv_service import TiendanubeCsvService

def folded(value):
    return unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().casefold()


def words(value):
    return re.findall(r"[a-z0-9]+", folded(value))


def brand_already_present(name, brand):
    """Match complete word sequences; avoid partial substrings and accent/case pitfalls."""
    name_words, brand_words = words(name), words(brand)
    return bool(brand_words) and any(
        name_words[i:i + len(brand_words)] == brand_words
        for i in range(len(name_words) - len(brand_words) + 1)
    )


def brand_partially_present(name, brand):
    name_words, brand_words = words(name), words(brand)
    if len(brand_words) < 2:
        return False
    return any(name_words[i:i + count] == brand_words[:count]
               for count in range(1, len(brand_words))
               for i in range(len(name_words) - count + 1))


def suggested_product_title(original_name, brand):
    """Do not invent SEO phrases or change source order without product evidence."""
    if not brand or brand_already_present(original_name, brand) or brand_partially_present(original_name, brand):
        return original_name
    return f"{original_name} · {brand}"


class TiendanubeEnrichmentProposalService:
    def __init__(self, db):
        self.catalog = TiendanubeCsvService(db)

    def report(self):
        rows = self.catalog.repo.snapshot("TIENDANUBE")
        if not rows:
            return {"available": False, "summary": {}, "items": []}
        grouped = {}
        for row in rows:
            key = str(row.get("slug") or "").strip()
            if not key:
                continue
            grouped.setdefault(key, []).append(row)
        proposals = []
        for key, variants in grouped.items():
            first = variants[0]
            original_name = str(first.get("name") or "").strip()
            if not original_name:
                continue
            brands = {str(x.get("brand") or "").strip() for x in variants if str(x.get("brand") or "").strip()}
            categories = {str(x.get("category") or "").strip() for x in variants if str(x.get("category") or "").strip()}
            brand = next(iter(brands)) if len(brands) == 1 else None
            category = next(iter(categories)) if len(categories) == 1 else None
            facts = [{"field": "name", "value": original_name, "source": "Tiendanube CSV"}]
            if brand:
                facts.append({"field": "brand", "value": brand, "source": "Tiendanube CSV"})
            if category:
                facts.append({"field": "category", "value": category, "source": "Tiendanube CSV"})
            reasons = []
            proposed_title = original_name
            if brand and not brand_already_present(original_name, brand):
                if brand_partially_present(original_name, brand):
                    reasons.append("El título contiene parte de la marca; requiere revisión para evitar duplicaciones.")
                else:
                    proposed_title = suggested_product_title(original_name, brand)
                    reasons.append("Se incorpora la marca del CSV sin repetirla ni modificar la descripción original.")
            if not any(x.get("description_present") for x in variants):
                reasons.append("No se detectó una descripción en el CSV.")
            if not reasons:
                continue
            proposals.append({
                "product_key": key, "original_name": original_name,
                "proposed_title": proposed_title,
                "title_changed": proposed_title != original_name,
                "seo_title": None,
                "seo_status": "PENDING_RESEARCH",
                "description_action": "RESEARCH_REQUIRED" if not any(
                    x.get("description_present") for x in variants) else "NO_CHANGE",
                "verified_product_facts": facts,
                "reasons": reasons,
                "status": "DRAFT_REVIEW",
                "policy": "Nombre comercial sugerido; título SEO y meta descripción requieren investigación. No valida datos de fabricante ni publica.",
            })
        counts = Counter("title" if x["title_changed"] else "description" for x in proposals)
        return {
            "available": True,
            "summary": {"proposals": len(proposals), "title_suggestions": counts["title"],
                        "description_research_needed": sum(
                            x["description_action"] == "RESEARCH_REQUIRED" for x in proposals)},
            "items": proposals,
            "policy": "No genera afirmaciones ni descripciones sin evidencia. Sin IA externa, sin publicación y sin cambios a las fuentes originales.",
        }
