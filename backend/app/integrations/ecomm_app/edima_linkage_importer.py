import re

from ..common.excel import ExcelImporter
from ...catalog.models import EdimaLinkageRow
from ...catalog.normalizer import normalize_ean, normalize_sku


class EdimaLinkageExcelImporter(ExcelImporter):
    """Read the EDIMA Mercado Libre inventory-linkage export from Ecomm-App."""

    source_label = "EDIMA Mercado Libre"
    required_any = {"external_id", "inventory_linked", "gtin_raw"}
    aliases = {
        "external_id": {
            "Nro. de la publicación",
            "Nro. de publicacion",
            "ID publicación",
            "ID publicacion",
            "MLA",
        },
        "variation_id": {"Id de la variación", "Id de la variacion"},
        "title": {"Título de la publicación", "Titulo de la publicacion", "Título", "Titulo"},
        "category": {"Categoría", "Categoria"},
        "brand": {"Marca", "Brand"},
        "inventory_linked": {
            "Publicacion Vinculada con Inventario",
            "Publicación Vinculada con Inventario",
        },
        "modified_at": {"Fecha Última Modificación", "Fecha Ultima Modificacion"},
        "gtin_raw": {
            "Codigo de Barras (GTIN)",
            "Código de Barras (GTIN)",
            "Codigo de Barras",
            "Código de Barras",
            "GTIN",
        },
    }

    def to_model(self, row, mapping):
        def get(key):
            return row[mapping[key]] if key in mapping else None

        def clean(value):
            return (
                str(value).strip()
                if value is not None and str(value).strip() != "nan"
                else None
            )

        gtin_raw = clean(get("gtin_raw"))
        gtins: list[str] = []
        for part in re.split(r"[,;\n]+", gtin_raw or ""):
            value = normalize_ean(part)
            if value and value not in gtins:
                gtins.append(value)

        return EdimaLinkageRow(
            external_id=normalize_sku(get("external_id")),
            variation_id=normalize_sku(get("variation_id")),
            title=clean(get("title")),
            category=clean(get("category")),
            brand=clean(get("brand")),
            inventory_linked=clean(get("inventory_linked")),
            modified_at=clean(get("modified_at")),
            gtin_raw=gtin_raw,
            gtins=gtins,
        )

    def accept(self, model) -> bool:
        return bool(model.external_id)

    def report_warnings(self, records):
        linked = sum(self._linked(record.inventory_linked) for record in records)
        unlinked = sum(self._unlinked(record.inventory_linked) for record in records)
        multiple = sum(len(record.gtins) > 1 for record in records)
        warnings = [
            f"EDIMA: {linked} publicaciones vinculadas y {unlinked} no vinculadas al inventario."
        ]
        if multiple:
            warnings.append(
                f"EDIMA: {multiple} publicaciones contienen más de un código de barras y requieren revisión."
            )
        return warnings

    @staticmethod
    def _linked(value) -> bool:
        return str(value or "").strip().casefold() in {"sí", "si", "yes"}

    @staticmethod
    def _unlinked(value) -> bool:
        return str(value or "").strip().casefold() in {"no"}
