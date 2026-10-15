"""Evidence-only commercial copy proposals; no LLM or external updates."""
from collections import Counter
from .tiendanube_csv_service import TiendanubeCsvService


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
            if brand and brand.casefold() not in original_name.casefold():
                proposed_title = f"{brand} · {original_name}"
                reasons.append("Marca explícita compatible, tomada del mismo producto.")
            if not any(x.get("description_present") for x in variants):
                reasons.append("No se detectó una descripción en el CSV.")
            if not reasons:
                continue
            proposals.append({
                "product_key": key, "original_name": original_name,
                "proposed_title": proposed_title,
                "title_changed": proposed_title != original_name,
                "description_action": "RESEARCH_REQUIRED" if not any(
                    x.get("description_present") for x in variants) else "NO_CHANGE",
                "verified_product_facts": facts,
                "reasons": reasons,
                "status": "DRAFT_REVIEW",
                "policy": "Borrador interno, armado solo con campos del CSV. No es validación de fabricante ni contenido publicado.",
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
