LABELS = {
    "ingredients": "Ingredientes",
    "allergens": "Alérgenos",
    "nutrition.energy": "Energía",
    "nutrition.protein": "Proteínas",
    "net_weight": "Contenido neto",
    "commercial_claim": "Declaración comercial",
}
REQUIRED = tuple(LABELS)
LABELS.update(
    {
        "width": "Ancho documentado",
        "nutrition.carbohydrates": "Hidratos de carbono",
        "nutrition.sugars": "Azúcares",
        "nutrition.total_fat": "Grasas totales",
        "nutrition.saturated_fat": "Grasas saturadas",
        "nutrition.fiber": "Fibra alimentaria",
        "nutrition.sodium": "Sodio",
        "certification": "Certificación declarada",
        "certification_evidence": "Respaldo documental de certificación",
    }
)
LABELS.update(
    {
        "storage_conditions": "Conservación",
        "characteristics": "Características verificables",
        "formulation": "Formulación",
    }
)
LABELS.update(
    {
        "product_name": "Nombre del alimento",
        "brand": "Marca",
        "manufacturer": "Fabricante",
        "presentation": "Presentación documentada",
        "category": "Categoría validada",
        "subcategory": "Subcategoría validada",
        "ean": "EAN individual documentado",
        "logistic_units": "Unidades de la caja logística (no pack comercial)",
        "logistic_dun": "DUN logístico (no EAN individual)",
    }
)
