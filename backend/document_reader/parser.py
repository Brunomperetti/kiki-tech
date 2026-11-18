"""No application imports, I/O or URLs: untrusted bytes -> bounded text and claims."""

from html.parser import HTMLParser
from io import BytesIO
import json
import re
import unicodedata
from decimal import Decimal

MAX_BYTES = 524_288
# Opt-in saved HTML originals can contain inert scripts/styles; other types stay at 512 KiB.
MAX_SAVED_HTML_BYTES = 4 * 1024 * 1024
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



class PageSnapshotHTML(HTMLParser):
    """Non-rendering extraction of a saved, source-preserved manufacturer page.

    A unique H1, an unambiguous size and a narrowly matched *literal*
    composition fragment are unapproved candidates. Product-specific
    WooCommerce descriptive sections are the only source for free text.
    No CSS/JS, resource fetch, inferred ingredients or nutritional claims.
    """

    OMIT = frozenset({
        "head", "script", "style", "noscript", "template", "svg", "iframe",
        "object", "embed", "form", "nav", "footer", "canvas",
    })
    VOID = frozenset({
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    })
    BLOCK = frozenset({"p", "li", "h1", "h2", "h3", "th", "td"})
    WEIGHT = re.compile(r"\d{1,5}(?:[.,]\d{1,3})?\s*(?:g|gr|kg|ml|l)\b", re.I)
    PRODUCT_AREAS = {
        "woocommerce-tabs", "woocommerce-product-details__short-description",
        "tab-description",
    }
    # Only clearly labelled, visible rows in the product's own WooCommerce
    # attribute table become candidates; all require later identity/provenance
    # review. Do not infer claims, certification, EAN, price or media rights.
    ATTRIBUTE_LABELS = {
        "marca": "Marca",
        "fabricante": "Fabricante",
        "ingredientes": "Ingredientes",
        "alergenos": "Alérgenos",
        "conservacion": "Conservación",
        "categoria": "Categoría",
        "subcategoria": "Subcategoría",
        "formulacion": "Formulación",
    }
    # Narrow pilot pattern: only an exact manufacturer sentence fragment,
    # never extended marketing prose or inferred specific ingredients.
    MIX_CLAIM = re.compile(
        r"\bcontiene\s+(\d{1,2}\s+frutos\s+secos\s*\+\s*"
        r"\d{1,2}\s+semillas\s+al\s+oreganato)\b", re.I,
    )

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags, self.omit = [], 0
        self.blocks, self.cells, self.headings = [], [], []
        self.captures = []
        self.tr_cells = []
        self.product_depth = 0
        self.events = 0
        self.total_text = 0

    def handle_starttag(self, tag, attrs):
        self.events += 1
        if self.events > 15000 or len(self.tags) > 100:
            raise ValueError("HTML de página demasiado complejo.")
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").lower().split())
        hidden = (
            tag in self.OMIT or "hidden" in attrs
            or (attrs.get("aria-hidden") or "").casefold() == "true"
            or bool(classes & {"hidden", "sr-only", "visually-hidden", "d-none", "screen-reader-text"})
            or bool(re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)",
                              attrs.get("style") or "", re.I))
        )
        if tag in self.VOID:
            return
        ignored = self.omit > 0 or hidden
        in_product = bool(
            self.product_depth or
            (classes & self.PRODUCT_AREAS) or
            (attrs.get("id") or "").lower() in self.PRODUCT_AREAS
        ) and not ignored
        is_attribute_table = (
            tag == "table" and self.product_depth > 0
            and "woocommerce-product-attributes" in classes
        )
        self.tags.append((tag, ignored, in_product, is_attribute_table))
        if ignored:
            self.omit += 1
            return
        if in_product:
            self.product_depth += 1
        if tag == "tr":
            self.tr_cells = []
        if tag in self.BLOCK:
            self.captures.append({
                "tag": tag, "text": [], "line": self.getpos()[0],
                "product_description": in_product,
            })

    def handle_endtag(self, tag):
        if not self.tags:
            return
        # A closing tag for unrelated markup must not end a hidden subtree.
        top, ignored, in_product, _ = self.tags[-1]
        if top != tag:
            return
        self.tags.pop()
        if ignored:
            self.omit -= 1
            return
        if in_product:
            self.product_depth -= 1
        if tag in self.BLOCK and self.captures and self.captures[-1]["tag"] == tag:
            active = self.captures.pop()
            value = " ".join(" ".join(active["text"]).split())
            if value:
                if tag == "h1":
                    self.headings.append((active["line"], value))
                elif tag in {"th", "td"} and "tr" in (x[0] for x in self.tags):
                    self.tr_cells.append(value)
                elif tag not in {"th", "td"}:
                    self.blocks.append((
                        tag, active["line"], value, active["product_description"]
                    ))
        if tag == "tr":
            # A random table (recommendations, upsell, freight or footer)
            # is never product evidence even when it has familiar labels.
            if (
                len(self.tr_cells) == 2
                and any(node[3] for node in self.tags)
                and len(self.cells) < 100
            ):
                self.cells.append(tuple(self.tr_cells))
            self.tr_cells = []

    def handle_data(self, data):
        if self.omit or not self.captures:
            return
        self.total_text += len(data)
        if self.total_text > MAX_TEXT:
            raise ValueError("Texto visible de página superior al límite.")
        for active in self.captures:
            active["text"].append(data)

    def sections(self):
        result = {}
        if len(self.headings) == 1:
            line, title = self.headings[0]
            if len(title) <= 180:
                result[f"web/h1/linea/{line}"] = "Nombre: " + title
        # Source-specific table data is considered only with a single visible
        # product H1. The table provides *candidate* facts, never approval.
        if len(self.headings) == 1:
            for i, row in enumerate(self.cells, 1):
                label, value = row[0].strip(), row[1].strip()
                clean_label = normalized(label).rstrip(":")
                if clean_label in {"peso", "presentacion", "contenido neto"}:
                    if len(value) <= 40 and self.WEIGHT.fullmatch(value):
                        result[f"web/tabla/fila/{i}"] = "Presentación: " + value
                elif clean_label in self.ATTRIBUTE_LABELS:
                    if (
                        1 <= len(value) <= 450
                        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
                        and not re.search(r"https?://|@", value, re.I)
                    ):
                        result[f"web/tabla/fila/{i}"] = (
                            self.ATTRIBUTE_LABELS[clean_label] + ": " + value
                        )
        for i, (tag, line, value, product_description) in enumerate(self.blocks, 1):
            if len(value) <= 2000:
                prefix = "web/product" if product_description and tag == "p" else "web"
                result[f"{prefix}/{tag}/linea/{line}/bloque/{i}"] = value
        return result



def pdf_sections(raw):
    from .hileret_brochure import matches, STREAM_LIMIT, TOTAL_STREAM_LIMIT

    pilot = matches(raw)
    stream_limit = STREAM_LIMIT if pilot else 1_048_576
    total_limit = TOTAL_STREAM_LIMIT if pilot else 2_097_152
    from pypdf import PdfReader, Configuration, overwrite_configuration
    from pypdf.generic import (
        IndirectObject,
        DictionaryObject,
        ArrayObject,
        StreamObject,
    )

    overwrite_configuration(
        Configuration(
            zlib_maximum_output_length=stream_limit,
            maximum_declared_stream_length=stream_limit,
            array_based_stream_maximum_output_length=stream_limit,
            stream_decoding_work_maximum_length=total_limit,
            stream_parsing_work_maximum_count=2_000_000 if pilot else 10000,
            array_maximum_element_count=3000,
            dictionary_maximum_element_count=3000,
            page_tree_maximum_entries=32,
            page_tree_maximum_depth=16,
            page_tree_maximum_page_entries=128 if pilot else 32,
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
        if count > (40000 if pilot else 10000) or depth > 40:
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
                if len(data) > stream_limit or streams > total_limit:
                    raise ValueError("PDF con expansión excesiva.")
            for value in obj.values():
                inspect(value, depth + 1)
        elif isinstance(obj, ArrayObject):
            for value in obj:
                inspect(value, depth + 1)

    inspect(reader.trailer)
    if len(reader.pages) > 10:
        raise ValueError("Máximo 10 páginas PDF.")
    if pilot:
        if len(reader.pages) != 4:
            raise ValueError(
                "El perfil Hileret requiere el original de cuatro páginas."
            )
        from .hileret_brochure import extract

        return extract(reader.pages[1])
    sections = {}
    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        if len(text) > MAX_TEXT:
            raise ValueError("Texto PDF excesivo.")
        for line, value in enumerate(text.splitlines(), 1):
            if value.strip():
                sections[f"pagina/{number}/linea/{line}"] = value.strip()
    return sections


def parse(name, mime, encoded, *, web_snapshot=False):
    extension = safe_filename(name)
    if mime != MIMES[extension]:
        raise ValueError("El MIME no corresponde a la extensión permitida.")
    from .hileret_brochure import validate_encoding, matches

    if web_snapshot and extension == ".html":
        import base64
        # Limit encoded size before allocating untrusted bytes.
        max_encoded = ((MAX_SAVED_HTML_BYTES + 2) // 3) * 4
        if len(encoded) > max_encoded:
            raise ValueError("HTML guardado superior a 4 MiB.")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (TypeError, ValueError):
            raise ValueError("Contenido base64 inválido.") from None
        if len(raw) > MAX_SAVED_HTML_BYTES:
            raise ValueError("HTML guardado superior a 4 MiB.")
    else:
        raw = validate_encoding(encoded)
    if not raw:
        raise ValueError("Archivo vacío o superior al límite de lectura.")
    json_values = None
    if extension == ".pdf":
        sections = pdf_sections(raw)
        if matches(raw):
            return sections  # bounded profile result, original bytes retained by the same ingester
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeError:
            raise ValueError("El documento debe usar UTF-8.") from None
        if (
            len(text) > (MAX_SAVED_HTML_BYTES if web_snapshot and extension == ".html" else MAX_TEXT)
            or any(ord(c) < 32 and c not in "\n\r\t" for c in text)
            or re.search("[\u202a-\u202e\u2066-\u2069]", text)
        ):
            raise ValueError("Texto excesivo o con controles inseguros.")
        if web_snapshot and extension != ".html":
            raise ValueError("Las capturas web solo admiten archivo HTML.")
        if extension == ".html":
            if web_snapshot:
                page = PageSnapshotHTML()
                page.feed(text)
                page.close()
                sections = page.sections()
            else:
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
            if ":" in line and (
                not (web_snapshot and extension == ".html")
                or loc.startswith(("web/h1/", "web/tabla/", "web/product/p/"))
            )
        ]
    )
    page_ambiguous = False
    if web_snapshot and extension == ".html":
        # Some authentic manufacturer pages publish presentation only in an
        # information paragraph, rather than WooCommerce attributes. Extract
        # a candidate ONLY when a unique visible H1 independently agrees on
        # count and form (e.g. 60 COMP == 60 comprimidos). Never extract
        # health benefits, dosage instructions, nutrition or medical claims.
        from .product_package import page_presentation

        package = page_presentation(sections)
        if package:
            presentation, location, quote = package
            entries.append(("presentación", presentation, None, location, quote))
        # Pages often publish composition in a description paragraph instead
        # of a labelled field. Keep only exact, brief, product-scoped fragments.
        # Never lift generic nutrition, health claims or nearby product cards.
        extracts = []
        for location, quote in sections.items():
            if not location.startswith("web/product/p/"):
                continue
            matches = list(PageSnapshotHTML.MIX_CLAIM.finditer(quote))
            for match in matches:
                extracts.append((match.group(1), location, quote))
        # Two differing composition claims are ambiguous, not a licence to
        # pick whichever one looks best.
        if len(extracts) == 1:
            value, location, quote = extracts[0]
            entries.append(("características", value, None, location, quote))
        elif len(extracts) > 1:
            page_ambiguous = True
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
    if page_ambiguous:
        warnings.append(
            "Más de una declaración descriptiva de composición: "
            "requiere revisión del original; no se extrajo característica."
        )
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
