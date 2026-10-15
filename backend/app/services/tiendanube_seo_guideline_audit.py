"""Read-only advisory checks based on Tiendanube's SEO e-commerce guide."""
import re


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\wÁÉÍÓÚÜÑáéíóúüñ]+\b", text or ""))


def audit_seo_fields(
    *, product_name: str, seo_title: str = "", meta_description: str = "",
    description: str = "", alt_text: str = "",
) -> dict:
    """Advisory limits, not publishability/validity checks."""
    alerts = []
    if seo_title and len(seo_title) > 60:
        alerts.append({"field": "seo_title", "reason": "Guía Tiendanube: referencia de 60 caracteres."})
    if meta_description and len(meta_description) > 150:
        alerts.append({"field": "meta_description", "reason": "Guía Tiendanube: referencia de 150 caracteres."})
    if alt_text and len(alt_text) > 60:
        alerts.append({"field": "alt_text", "reason": "Guía Tiendanube: referencia de 60 caracteres."})
    count = word_count(description)
    if description and not 100 <= count <= 300:
        alerts.append({"field": "description", "reason": "Guía Tiendanube: sugerencia editorial de 100 a 300 palabras."})
    missing = [field for field, value in {
        "product_name": product_name,
        "seo_title": seo_title,
        "meta_description": meta_description,
        "description": description,
        "alt_text": alt_text,
    }.items() if not value.strip()]
    return {
        "alerts": alerts, "missing": missing,
        "description_words": count,
        "status": "ADVISORY_ONLY",
        "policy": "No verifica hechos ni imágenes; no genera textos, no publica ni modifica productos.",
    }
