"""No application imports, I/O or URLs: untrusted bytes -> bounded text and claims."""

import base64
from html.parser import HTMLParser
from io import BytesIO
import json
import re
import unicodedata
from decimal import Decimal

MAX_BYTES = 524_288
MAX_TEXT = 65_536
MIMES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".html": "text/html",
    ".json": "application/json",
}
ALIASES = {
    "ancho": "width",
    "valor energetico": "nutrition.energy",
    "hidratos de carbono": "nutrition.carbohydrates",
    "carbohidratos": "nutrition.carbohydrates",
    "azucares": "nutrition.sugars",
    "grasas totales": "nutrition.total_fat",
    "grasas saturadas": "nutrition.saturated_fat",
    "fibra alimentaria": "nutrition.fiber",
    "fibra": "nutrition.fiber",
    "sodio": "nutrition.sodium",
    "certificacion": "certification",
    "respaldo de certificacion": "certification_evidence",
    "nombre": "product_name",
    "nombre comercial": "product_name",
    "product_name": "product_name",
    "marca": "brand",
    "brand": "brand",
    "fabricante": "manufacturer",
    "manufacturer": "manufacturer",
    "ean": "ean",
    "presentacion": "presentation",
    "presentation": "presentation",
    "ingredientes": "ingredients",
    "ingredients": "ingredients",
    "alergenos": "allergens",
    "allergens": "allergens",
    "energia": "nutrition.energy",
    "energy": "nutrition.energy",
    "proteinas": "nutrition.protein",
    "contenido neto": "net_weight",
    "net_weight": "net_weight",
    "conservacion": "storage_conditions",
    "caracteristicas": "characteristics",
    "declaracion comercial": "commercial_claim",
    "categoria": "category",
    "subcategoria": "subcategory",
    "formulacion": "formulation",
    "tipo de venta": "sale_type",
}


def normalized(value):
    return (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode()
        .lower()
        .strip()
    )


def safe_filename(name):
    if (
        not name
        or len(name) > 120
        or name.startswith(".")
        or ".." in name
        or any(not (c.isalnum() or c in " ._-") for c in name)
    ):
        raise ValueError(
            "Nombre de archivo inseguro; no se aceptan rutas ni controles."
        )
    extension = "." + name.rsplit(".", 1)[-1].lower()
    if extension not in MIMES:
        raise ValueError("Tipo no permitido. Usá PDF, TXT UTF-8, HTML pasivo o JSON.")
    return extension


class PassiveHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.fragments, self.depth, self.count = [], 0, 0
        self.current, self.position = [], (1, 0)

    def flush(self):
        text = " ".join(" ".join(self.current).split())
        if text:
            self.fragments.append(
                (f"html/linea/{self.position[0]}/bloque/{len(self.fragments)+1}", text)
            )
        self.current = []

    def handle_starttag(self, tag, attrs):
        self.count += 1
        if tag not in {
            "html",
            "head",
            "title",
            "body",
            "main",
            "section",
            "p",
            "div",
            "span",
            "br",
            "h1",
            "h2",
            "h3",
            "strong",
            "b",
            "em",
            "ul",
            "li",
            "table",
            "tr",
            "td",
            "th",
        }:
            raise ValueError(
                "HTML activo o no soportado; exportá texto o PDF sin contenido activo."
            )
        if attrs:
            raise ValueError(
                "HTML con atributos/recursos rechazado; se admite sólo HTML pasivo sin atributos."
            )
        if tag in {"p", "div", "br", "h1", "h2", "h3", "li", "tr"}:
            self.flush()
        if tag != "br":
            self.depth += 1
        if self.depth > 32 or self.count > 2000:
            raise ValueError("HTML excesivamente complejo.")

    def handle_endtag(self, tag):
        if tag in {"p", "div", "h1", "h2", "h3", "li", "tr"}:
            self.flush()
        self.depth = max(0, self.depth - 1)

    def handle_data(self, value):
        if not self.current:
            self.position = self.getpos()
        self.current.append(value)


def pdf_sections(raw):
    from pypdf import PdfReader, Configuration, overwrite_configuration
    from pypdf.generic import (
        IndirectObject,
        DictionaryObject,
        ArrayObject,
        StreamObject,
    )

    overwrite_configuration(
        Configuration(
            zlib_maximum_output_length=1_048_576,
            maximum_declared_stream_length=1_048_576,
            array_based_stream_maximum_output_length=1_048_576,
            stream_decoding_work_maximum_length=2_097_152,
            stream_parsing_work_maximum_count=10000,
            array_maximum_element_count=3000,
            dictionary_maximum_element_count=3000,
            page_tree_maximum_entries=32,
            page_tree_maximum_depth=16,
            page_tree_maximum_page_entries=32,
            xform_maximum_invocations_per_extraction=64,
            jbig2dec_binary=None,
        )
    )
    if not raw.startswith(b"%PDF-") or b"%%EOF" not in raw[-1024:]:
        raise ValueError("Firma PDF inválida o archivo truncado.")
    reader = PdfReader(
        BytesIO(raw),
        strict=True,
        root_object_recovery_limit=0,
        xref_stream_maximum_entries=3000,
    )
    if reader.is_encrypted:
        raise ValueError("PDF cifrado no soportado.")
    if sum(len(row) for row in reader.xref.values()) + len(reader.xref_objStm) > 3000:
        raise ValueError("PDF con demasiados objetos.")
    seen, count, streams = set(), 0, 0

    def inspect(obj, depth=0):
        nonlocal count, streams
        count += 1
        if count > 10000 or depth > 40:
            raise ValueError("PDF excesivamente complejo.")
        if isinstance(obj, IndirectObject):
            if obj.idnum in seen:
                return
            seen.add(obj.idnum)
            inspect(obj.get_object(), depth + 1)
        elif isinstance(obj, DictionaryObject):
            if set(obj) & {
                "/JavaScript",
                "/JS",
                "/Launch",
                "/OpenAction",
                "/AA",
                "/EmbeddedFiles",
                "/EmbeddedFile",
                "/RichMedia",
                "/XFA",
                "/SubmitForm",
                "/URI",
                "/A",
                "/AF",
            }:
                raise ValueError(
                    "PDF con acciones, enlaces activos o adjuntos rechazado."
                )
            if isinstance(obj, StreamObject) and obj.get("/Subtype") != "/Image":
                # Restrict supported compression before any decode, including hidden streams.
                encoding = obj.get("/Filter")
                if encoding not in (None, "/FlateDecode"):
                    raise ValueError("PDF con codificación de stream no soportada.")
                data = obj.get_data()
                streams += len(data)
                if len(data) > 1_048_576 or streams > 2_097_152:
                    raise ValueError("PDF con expansión excesiva.")
            for value in obj.values():
                inspect(value, depth + 1)
        elif isinstance(obj, ArrayObject):
            for value in obj:
                inspect(value, depth + 1)

    inspect(reader.trailer)
    if len(reader.pages) > 10:
        raise ValueError("Máximo 10 páginas PDF.")
    sections = {}
    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        if len(text) > MAX_TEXT:
            raise ValueError("Texto PDF excesivo.")
        for line, value in enumerate(text.splitlines(), 1):
            if value.strip():
                sections[f"pagina/{number}/linea/{line}"] = value.strip()
    return sections


def parse(name, mime, encoded):
    extension = safe_filename(name)
    if mime != MIMES[extension]:
        raise ValueError("El MIME no corresponde a la extensión permitida.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        raise ValueError("Contenido base64 inválido.") from None
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("Archivo vacío o superior a 512 KiB.")
    json_values = None
    if extension == ".pdf":
        sections = pdf_sections(raw)
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeError:
            raise ValueError("El documento debe usar UTF-8.") from None
        if (
            len(text) > MAX_TEXT
            or any(ord(c) < 32 and c not in "\n\r\t" for c in text)
            or re.search("[\u202a-\u202e\u2066-\u2069]", text)
        ):
            raise ValueError("Texto excesivo o con controles inseguros.")
        if extension == ".html":
            html = PassiveHTML()
            html.feed(text)
            html.flush()
            sections = dict(html.fragments)
        elif extension == ".json":
            data = json.loads(text)
            if not isinstance(data, dict) or len(data) > 40:
                raise ValueError("JSON requiere un objeto plano de hasta 40 campos.")
            sections, json_values = {}, []
            for key, value in data.items():
                if not isinstance(key, str) or len(key) > 80:
                    raise ValueError("Clave JSON inválida.")
                if isinstance(value, dict):
                    if set(value) != {"valor", "unidad"} or not all(
                        isinstance(v, str) for v in value.values()
                    ):
                        raise ValueError(
                            "Los datos estructurados usan {valor,unidad}, ambos textos."
                        )
                    literal, unit = value["valor"], value["unidad"]
                elif isinstance(value, str):
                    literal, unit = value, None
                else:
                    raise ValueError(
                        "No se aceptan JSON anidados, código ni valores no textuales."
                    )
                location = "json/" + key.replace("~", "~0").replace("/", "~1")
                quote = json.dumps({key: value}, ensure_ascii=False)
                sections[location] = quote
                json_values.append((key, literal, unit, location, quote))
        else:
            if text.lstrip().startswith(("<", "%PDF-", "PK")):
                raise ValueError("La firma no corresponde a texto plano.")
            sections = {
                f"texto/linea/{i}": value.strip()
                for i, value in enumerate(text.splitlines(), 1)
                if value.strip()
            }
    if (
        len(sections) > 1000
        or sum(map(len, sections.values())) > MAX_TEXT
        or any(len(v) > 2000 for v in sections.values())
    ):
        raise ValueError("Demasiado texto, líneas o contenido por fragmento.")
    if any(
        any(ord(c) < 32 and c not in "\n\r\t" for c in value)
        or re.search("[\u202a-\u202e\u2066-\u2069]", value)
        for value in sections.values()
    ):
        raise ValueError("Contenido con controles inseguros.")
    entries = (
        json_values
        if json_values is not None
        else [
            (line.split(":", 1)[0], line.split(":", 1)[1].strip(), None, loc, line)
            for loc, line in sections.items()
            if ":" in line
        ]
    )
    if json_values is None:
        # A bounded single row of a passive HTML/PDF nutritional table, never pair unrelated lines.
        for loc, line in sections.items():
            if ":" in line:
                continue
            row = re.fullmatch(
                r"(.+?)\s+(\d+(?:[.,]\d+)?\s*(?:kcal|kj|g|mg|µg)(?:\s*/\s*(?:100\s*(?:g|ml)|porci[oó]n))?)",
                line,
                re.IGNORECASE,
            )
            if row and ALIASES.get(normalized(row[1]), "").startswith("nutrition."):
                entries.append((row[1], row[2], None, loc, line))
    values, warnings, ambiguous = {}, [], set()
    for label, literal, unit, location, quote in entries:
        field = ALIASES.get(normalized(label))
        if not field or not literal.strip():
            continue
        value = literal.strip()
        if field.startswith("nutrition.") or field in {"net_weight", "width"}:
            match = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(.*)", value)
            if match and unit is None:
                value, unit = match[1], match[2] or None
        if (
            field.startswith("nutrition.")
            and unit
            and not re.fullmatch(
                (r"(?:kcal|kj)" if field == "nutrition.energy" else r"(?:g|mg|µg)")
                + r"(?:\s*/\s*(?:100\s*(?:g|ml)|porci[oó]n))?",
                unit,
                re.IGNORECASE,
            )
        ):
            unit = None  # arbitrary trailing prose is not a nutritional unit
        candidate = {
            "field": field,
            "value": value,
            "unit": unit or None,
            "location": location,
            "quote": quote,
        }
        if field in values and (values[field]["value"], values[field]["unit"]) != (
            value,
            unit or None,
        ):
            ambiguous.add(field)
        else:
            values[field] = candidate
    for field in ambiguous:
        values.pop(field, None)
        warnings.append(f"Valores contradictorios dentro del documento: {field}.")
    identity = {
        key: values[field]["value"] if field in values else None
        for key, field in {
            "name": "product_name",
            "brand": "brand",
            "manufacturer": "manufacturer",
            "ean": "ean",
            "presentation": "presentation",
        }.items()
    }
    sale = values.get("sale_type", {}).get("value")
    identity["is_combo"] = {"unidad": False, "pack": True}.get(normalized(sale or ""))
    weight = values.get("net_weight")
    plain = re.fullmatch(
        r"(\d+(?:[.,]\d+)?)\s*(g|kg|ml|l)",
        normalized(identity.get("presentation") or ""),
    )
    if weight and plain and identity["is_combo"] is False:
        units = {
            "g": ("masa", Decimal(1)),
            "kg": ("masa", Decimal(1000)),
            "ml": ("volumen", Decimal(1)),
            "l": ("volumen", Decimal(1000)),
        }
        unit = normalized(weight["unit"] or "")
        if unit and unit not in units:
            warnings.append(
                "Unidad de contenido neto no contrastable con esta presentación; requiere procesamiento adicional."
            )
        if unit in units and re.fullmatch(r"\d+(?:[.,]\d+)?", weight["value"]):
            expected_kind, factor = units[plain[2]]
            actual_kind, actual_factor = units[unit]
            if (
                expected_kind != actual_kind
                or Decimal(plain[1].replace(",", ".")) * factor
                != Decimal(weight["value"].replace(",", ".")) * actual_factor
            ):
                warnings.append(
                    "Contenido neto incompatible con el peso/volumen explícito de la presentación."
                )
    claims = [
        {
            **v,
            "presentation": identity["presentation"],
            "commercial_field": v["field"]
            if v["field"]
            in {"brand", "manufacturer", "presentation", "category", "subcategory"}
            else "attributes",
        }
        for v in values.values()
        if v["field"] not in {"ean", "sale_type"}
    ]
    return {
        "sections": sections,
        "identity": identity,
        "identity_evidence": {
            key: values[field]
            for key, field in {
                "name": "product_name",
                "brand": "brand",
                "manufacturer": "manufacturer",
                "ean": "ean",
                "presentation": "presentation",
                "sale_type": "sale_type",
            }.items()
            if field in values
        },
        "claims": claims,
        "parser_warnings": warnings,
        "parser_blockers": warnings,
        "parse_status": "NEEDS_OCR"
        if extension == ".pdf" and not sections
        else "TEXT_EXTRACTED"
        if claims
        else "INSUFFICIENT_DATA",
    }
