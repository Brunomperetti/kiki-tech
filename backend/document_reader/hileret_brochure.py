"""One user-supplied original, identified by bytes; never an origin approval."""

import base64
import hashlib
import re

SHA256 = "bd99c29548cbf683e57b1fd6f2973f37ccef76477e2f6bc45379017a63599291"
SIZE = 6_232_081
ENCODED_SIZE = ((SIZE + 2) // 3) * 4
MAX_REQUEST = ENCODED_SIZE + 8192
MAX_HTTP_BODY = MAX_REQUEST + 8192
STREAM_LIMIT = 5 * 1024 * 1024
TOTAL_STREAM_LIMIT = 16 * 1024 * 1024
PROFILE = "hileret-original-page2-v1"


def matches(raw):
    return len(raw) == SIZE and hashlib.sha256(raw).hexdigest() == SHA256


def validate_encoding(encoded):
    if len(encoded) > ENCODED_SIZE:
        raise ValueError("Contenido superior al límite del piloto Hileret.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        raise ValueError("Contenido base64 inválido.") from None
    if len(raw) > 524_288 and not matches(raw):
        raise ValueError(
            "Se mantiene el límite de 512 KiB: sólo el original Hileret autorizado por SHA-256 admite ampliación."
        )
    return raw


def extract(page):
    """Read exact native cells, never adjacent columns flattened into fake rows."""
    cells = []

    def visitor(text, cm, tm, font, size):
        value = text.strip()
        if not value:
            return
        x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
        y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
        if not (0 <= x <= 482 and 0 <= y <= 709) or len(value) > 2000:
            raise ValueError("Coordenadas o fragmento fuera del perfil documental.")
        cells.append((x, y, value))
        if len(cells) > 1000:
            raise ValueError("Demasiados fragmentos PDF.")

    page.extract_text(visitor_text=visitor)

    def cell(x0, x1, y0, y1):
        found = [
            (x, y, text) for x, y, text in cells if x0 <= x <= x1 and y0 <= y <= y1
        ]
        if len(found) != 1:
            raise ValueError(
                "Celda ausente o ambigua; no se mezclan filas de otros productos."
            )
        return found[0]

    header = cell(30, 34, 119, 121)
    if not header[2].startswith("Producto Familia EAN DUN "):
        raise ValueError("Cabeceras de la tabla Stevia no reconocidas.")
    product = cell(30, 34, 40, 42)
    match = re.fullmatch(r"(Hileret Stevia) (\d+) x (\d+ ml)", product[2])
    if not match:
        raise ValueError("Fila de Stevia no reconocida.")
    caption = cell(438, 440, 152, 154)
    ean, dun = cell(141, 145, 40, 42), cell(189, 193, 40, 42)
    if (
        caption[2] != match[3]
        or not re.fullmatch(r"\d{13}", ean[2])
        or not re.fullmatch(r"\d{14}", dun[2])
    ):
        raise ValueError("Identificadores o volumen no contrastables.")
    sections = {}

    def evidence(label, item):
        x, y, text = item
        location = f"pagina/2/tabla/stevia/fila/liquido-200ml/columna/{label}/x{x:.2f}/y{y:.2f}"
        sections[location] = text
        return location

    product_loc = evidence("producto", product)
    caption_loc = evidence("rotulo-envase", caption)
    ean_loc, dun_loc = evidence("EAN", ean), evidence("DUN", dun)
    evidence("cabeceras", header)
    claims = []

    def claim(field, value, location, unit=None):
        claims.append(
            {
                "field": field,
                "value": value,
                "unit": unit,
                "presentation": caption[2],
                "location": location,
                "quote": sections[location],
                "commercial_field": field
                if field in {"brand", "presentation"}
                else "attributes",
            }
        )

    claim("product_name", match[1], product_loc)
    claim("brand", match[1].split()[0], product_loc)
    claim("presentation", caption[2], caption_loc)
    claim("net_weight", caption[2].split()[0], caption_loc, "ml")
    claim("ean", ean[2], ean_loc)
    claim("logistic_units", match[2], product_loc)
    claim("logistic_dun", dun[2], dun_loc)
    return {
        "sections": sections,
        "identity": {
            "name": match[1],
            "brand": match[1].split()[0],
            "manufacturer": None,
            "presentation": caption[2],
            "ean": ean[2],
            "is_combo": False,
        },
        "identity_evidence": {
            "name": claims[0],
            "brand": claims[1],
            "presentation": claims[2],
            "ean": claims[4],
        },
        "claims": claims,
        "parser_warnings": [],
        "parser_blockers": [],
        "parse_status": "TEXT_EXTRACTED",
        "extraction_profile": PROFILE,
        "scope_note": "Página 2, tabla Stevia, fila Hileret Stevia 9 x 200 ml y rótulo 200 ml del envase. El objetivo es la unidad individual; x9 y DUN son logísticos, no pack x6. Sin ingredientes, nutrición o certificaciones.",
    }
