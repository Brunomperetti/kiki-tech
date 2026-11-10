"""Independent authored manufacturer/search responses. Not facts from query input."""

from pathlib import Path
import json
from .discovery_http import Response
from .research.documents import BRAND, MANUFACTURER

PRODUCTS = [
    (
        "almendras-250",
        "Almendras sintéticas",
        "250 g",
        "12345670",
        "Almendras",
        "250",
        "g",
    ),
    (
        "almendras-1000",
        "Almendras sintéticas",
        "1 kg",
        "12345687",
        "Almendras",
        "1000",
        "g",
    ),
    (
        "chia-250",
        "Semillas de chía sintéticas",
        "250 g",
        "2000000000039",
        "Semillas de chía",
        "250",
        "g",
    ),
    (
        "harina-1000",
        "Harina integral sintética",
        "1 kg",
        "2000000000046",
        "Harina integral",
        "1000",
        "g",
    ),
    ("avena-500", "Avena sintética", "500 g", "2000000000053", "Avena", "500", "g"),
    (
        "lentejas-1000",
        "Lentejas sintéticas",
        "1 kg",
        "2000000000060",
        "Lentejas",
        "1000",
        "g",
    ),
]


def catalogue():
    entries, responses = [], {}
    kinds = [
        ("sitio", "Sitio del fabricante", "text/html"),
        ("tecnica", "Ficha técnica", "text/plain"),
        ("etiqueta", "Etiqueta", "application/json"),
        ("catalogo", "Catálogo", "text/plain"),
        ("comercial", "Documento comercial", "text/plain"),
        ("pista", "Pista pública", "text/plain"),
        ("otro-fabricante", "Ficha técnica", "text/plain"),
        ("contradiccion", "Tabla nutricional contradictoria", "text/plain"),
        ("insuficiente", "Documento insuficiente", "text/plain"),
    ]
    for key, name, presentation, ean, ingredients, weight, unit in PRODUCTS:
        for subtype, kind, mime in kinds:
            host = (
                "pista-publica.invalid"
                if subtype == "pista"
                else "fabricante-prueba.invalid"
            )
            url = f"https://{host}/{key}/{subtype}"
            manufacturer = (
                "Otro fabricante sintético"
                if subtype == "otro-fabricante"
                else MANUFACTURER
            )
            identity = {
                "name": name,
                "brand": BRAND,
                "manufacturer": manufacturer,
                "ean": ean,
                "presentation": presentation,
                "net_weight": f"{weight} {unit}",
                "is_combo": False,
            }
            values = {
                "Nombre": name,
                "Marca": BRAND,
                "Fabricante": manufacturer,
                "EAN": ean,
                "Presentación": presentation,
                "Tipo de venta": "Unidad",
                "Ingredientes": ingredients,
                "Alérgenos": "Consultar etiqueta sintética específica",
                "Energía": "610 kcal/100 g"
                if subtype == "contradiccion"
                else "600 kcal/100 g",
                "Proteínas": "20 g/100 g",
                "Hidratos de carbono": "30 g/100 g",
                "Azúcares": "5 g/100 g",
                "Grasas totales": "40 g/100 g",
                "Grasas saturadas": "4 g/100 g",
                "Fibra alimentaria": "8 g/100 g",
                "Sodio": "10 mg/100 g",
                "Contenido neto": f"{weight} {unit}",
                "Conservación": "Conservar en lugar fresco y seco",
                "Características": "Producto sintético para pruebas",
                "Certificación": "Sin gluten",
                "Respaldo de certificación": "Certificado ficticio SG-PRUEBA-001; no es una certificación real",
            }
            if subtype == "insuficiente":
                raw = b"Documento sintetico sin identidad ni datos suficientes."
            elif mime == "application/json":
                raw = json.dumps(values, ensure_ascii=False).encode()
            elif mime == "text/html":
                raw = (
                    "<html><body>"
                    + "".join(f"<p>{k}: {v}</p>" for k, v in values.items())
                    + "</body></html>"
                ).encode()
            else:
                raw = "\n".join(f"{k}: {v}" for k, v in values.items()).encode()
            # One real PDF format fixture accompanies the synthetic plain/HTML/JSON responses.
            if key == "harina-1000" and subtype == "tecnica":
                raw = (
                    Path(__file__).parent / "discovery-fixtures/harina-tecnica.pdf"
                ).read_bytes()
                mime = "application/pdf"
            final = f"https://documentos-prueba.invalid/{key}/{subtype}"
            responses[url] = (
                Response(302, location=final)
                if subtype == "tecnica"
                else Response(200, raw, mime)
            )
            if subtype == "tecnica":
                responses[final] = Response(200, raw, mime)
            entries.append(
                {
                    "source_id": f"{key}-{subtype}",
                    "url": url,
                    "kind": kind,
                    "priority": {
                        "sitio": 0,
                        "tecnica": 1,
                        "etiqueta": 2,
                        "catalogo": 3,
                        "comercial": 4,
                        "pista": 5,
                    }.get(subtype, 6),
                    "declared_official": subtype != "pista",
                    "identity_hint": identity,
                    "title": f"{kind} · {name} · {presentation} · SIMULADO",
                    "content_type_hint": mime,
                    "simulated": True,
                    "rights": "Documento inventado para esta demostración.",
                }
            )
    return entries, responses
