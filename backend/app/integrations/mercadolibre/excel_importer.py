from ..common.excel import ExcelImporter
from ...catalog.models import ChannelListing
from ...catalog.normalizer import normalize_decimal, normalize_ean, normalize_sku


class MercadoLibreExcelImporter(ExcelImporter):
    source_label = "Mercado Libre"
    required_any = {"external_id", "sku_product", "sku_variant", "ean"}
    aliases = {
        "external_id": {
            "ID publicación",
            "ID publicacion",
            "Nro. de la publicación",
            "MLA",
            "ID",
        },
        "sku_product": {"SKU", "Código SKU", "Codigo SKU", "Seller SKU"},
        "sku_variant": {"SKU de la Variante", "SKU variante"},
        "ean": {"EAN", "GTIN", "Código universal", "Codigo universal"},
        "title": {
            "Título",
            "Titulo",
            "Título de la publicación",
            "Publicación",
            "Producto",
        },
        "status": {"Estado", "Status"},
        "price": {"Precio", "Price"},
        "url": {"URL", "Link", "Permalink"},
        "inventory_linked": {
            "Publicacion Vinculada con Inventario",
            "Publicación Vinculada con Inventario",
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

        sku_product = normalize_sku(get("sku_product"))
        variant_sku = normalize_sku(get("sku_variant"))
        return ChannelListing(
            external_id=normalize_sku(get("external_id")),
            sku=variant_sku or sku_product,
            sku_product=sku_product,
            variant_sku=variant_sku,
            sku_effective=variant_sku or sku_product,
            sku_source="sku_variant"
            if variant_sku
            else "sku_product"
            if sku_product
            else None,
            ean=normalize_ean(get("ean")),
            title=clean(get("title")),
            status=clean(get("status")),
            price=normalize_decimal(get("price")),
            url=clean(get("url")),
            inventory_linked=clean(get("inventory_linked")),
        )
