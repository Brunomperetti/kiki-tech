"""Authored fixtures, never downloaded manufacturer or label data."""

from copy import deepcopy

BRAND = "Marca sintética KIKI"
MANUFACTURER = "Fabricante de prueba"
LABELS = {
    "ingredients": "Ingredientes",
    "allergens": "Alérgenos",
    "nutrition.energy": "Energía",
    "nutrition.protein": "Proteínas",
    "net_weight": "Contenido neto",
    "commercial_claim": "Declaración comercial",
}
REQUIRED = tuple(LABELS)


def document(
    ident, title, kind, claims, *, presentation="250 g", ean="12345670", version=1
):
    sections = {
        "identidad": f"DOCUMENTO SINTÉTICO DE PRUEBA. Almendras sintéticas. {BRAND}. {MANUFACTURER}. Presentación {presentation}. EAN de prueba {ean}."
    }
    rows = []
    for field, value, unit, quote in claims:
        location = f"datos/{field}"
        sections[location] = quote
        rows.append(
            {
                "field": field,
                "commercial_field": "attributes",
                "value": value,
                "unit": unit,
                "presentation": presentation,
                "location": location,
                "quote": quote,
            }
        )
    return {
        "id": ident,
        "version": version,
        "title": title,
        "kind": kind,
        "synthetic": True,
        "provenance": f"fixture://kiki-research/{ident}/v{version}",
        "identity": {
            "name": "Almendras sintéticas",
            "brand": BRAND,
            "manufacturer": MANUFACTURER,
            "ean": ean,
            "presentation": presentation,
        },
        "sections": sections,
        "claims": rows,
    }


TECH = document(
    "alm-tecnica",
    "Ficha técnica de fabricante · PRUEBA",
    "Ficha técnica",
    [
        (
            "ingredients",
            "Almendras",
            None,
            "Ingredientes: Almendras. Información inventada de prueba.",
        ),
        (
            "allergens",
            "Contiene almendras",
            None,
            "Alérgenos: Contiene almendras. Texto sintético.",
        ),
        (
            "nutrition.energy",
            "600",
            "kcal/100 g",
            "Energía: 600 kcal/100 g. Tabla inventada para pruebas.",
        ),
        (
            "nutrition.protein",
            "20",
            "g/100 g",
            "Proteínas: 20 g/100 g. Dato inventado.",
        ),
        ("net_weight", "250", "g", "Contenido neto: 250 g. Presentación sintética."),
        (
            "commercial_claim",
            "Sin sal agregada",
            None,
            "Declaración comercial: Sin sal agregada. Ejemplo ficticio, no usar comercialmente.",
        ),
    ],
)
TECH_V2 = deepcopy(TECH)
TECH_V2.update(version=2, provenance="fixture://kiki-research/alm-tecnica/v2")
TECH_V2["claims"][2].update(
    value="620", quote="Energía: 620 kcal/100 g. Revisión sintética del documento."
)
TECH_V2["sections"]["datos/nutrition.energy"] = TECH_V2["claims"][2]["quote"]
TECH_V3 = deepcopy(TECH_V2)
TECH_V3.update(version=3, provenance="fixture://kiki-research/alm-tecnica/v3")
TECH_V3["claims"][2].update(
    value="640",
    quote="Energía: 640 kcal/100 g. Tercera revisión exclusivamente sintética.",
)
TECH_V3["sections"]["datos/nutrition.energy"] = TECH_V3["claims"][2]["quote"]

FIXTURES = {
    "alm-tecnica": [TECH, TECH_V2, TECH_V3],
    "alm-etiqueta": [
        document(
            "alm-etiqueta",
            "Etiqueta de producto · PRUEBA",
            "Etiqueta",
            [
                (
                    "allergens",
                    "Contiene almendras",
                    None,
                    "Etiqueta sintética: Contiene almendras.",
                )
            ],
        )
    ],
    "alm-ingredientes": [
        document(
            "alm-ingredientes",
            "Información de ingredientes · PRUEBA",
            "Ingredientes",
            [("ingredients", "Almendras", None, "Ingredientes de prueba: Almendras.")],
        )
    ],
    "alm-nutricion-conflicto": [
        document(
            "alm-nutricion-conflicto",
            "Tabla nutricional contradictoria · PRUEBA",
            "Tabla nutricional",
            [
                (
                    "nutrition.energy",
                    "610",
                    "kcal/100 g",
                    "Tabla sintética alternativa: 610 kcal/100 g.",
                )
            ],
        )
    ],
    "alm-incompleta": [
        document(
            "alm-incompleta",
            "Documento insuficiente · PRUEBA",
            "Tabla incompleta",
            [
                (
                    "nutrition.energy",
                    "500",
                    None,
                    "Energía: 500. Unidad ausente en esta prueba.",
                ),
                (
                    "commercial_claim",
                    "Orgánico",
                    None,
                    "El documento sintético no informa ninguna declaración comercial.",
                ),
            ],
        )
    ],
    "alm-pack-1kg": [
        document(
            "alm-pack-1kg",
            "Presentación y contenido neto 1 kg · PRUEBA",
            "Presentación",
            [("net_weight", "1000", "g", "Contenido neto de prueba: 1000 g.")],
            presentation="1 kg",
            ean="12345685",
        )
    ],
    "alm-ean-incompatible": [
        document(
            "alm-ean-incompatible",
            "Etiqueta con EAN incompatible · PRUEBA",
            "Etiqueta",
            [
                (
                    "allergens",
                    "Contiene almendras",
                    None,
                    "Etiqueta de prueba: Contiene almendras.",
                )
            ],
            ean="12345685",
        )
    ],
}

# A changed source is deliberately different from reimporting a rejected source.
ALT_V2 = deepcopy(FIXTURES["alm-nutricion-conflicto"][0])
ALT_V2.update(
    version=2, provenance="fixture://kiki-research/alm-nutricion-conflicto/v2"
)
ALT_V2["claims"][0].update(
    value="611", quote="Tabla sintética alternativa revisada: 611 kcal/100 g."
)
ALT_V2["sections"]["datos/nutrition.energy"] = ALT_V2["claims"][0]["quote"]
FIXTURES["alm-nutricion-conflicto"].append(ALT_V2)
