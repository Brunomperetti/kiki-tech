from ..common.excel import ExcelImporter
from ...catalog.models import EcommChannelRow
from ...catalog.normalizer import normalize_decimal, normalize_ean, normalize_sku


class EcommExcelImporter(ExcelImporter):
    source_label = "Ecomm-App"
    required_any = {"sku_product", "sku_variant", "ean"}
    aliases = {
        "ecomm_id": {"ID", "ID producto", "Código interno", "ID interno (no cambiar)"},
        "sku_product": {
            "SKU",
            "SKU producto",
            "SKU del Producto",
            "Código SKU",
            "Codigo SKU",
        },
        "sku_variant": {"SKU variante", "SKU de la variante"},
        "ean": {"EAN", "GTIN", "Código de barra", "Codigo de barras", "Barcode"},
        "name": {
            "Nombre",
            "Producto",
            "Descripción",
            "Descripcion",
            "Descripción del producto",
        },
        "brand": {"Marca", "Brand"},
        # Both prices are row data; canonicalization decides their product meaning.
        "price_marketplace": {"Precio Marketplace", "Precio", "Precio venta"},
        "price_list": {"Precio Lista", "Precio de lista"},
        "cost": {"Costo", "Cost", "Costo del producto"},
        "stock": {"Stock", "Inventario", "Cantidad", "General"},
        "marketplace": {"MarketPlace", "Marketplace"},
        "marketplace_id": {"Id MarketPlace", "ID Marketplace"},
        "store": {"Tienda"},
        "listing_id": {"Nro. de la publicación", "Nro. de publicacion"},
        "listing_title": {"Título de la publicación", "Titulo de la publicacion"},
        "listing_status": {"Estado", "Status"},
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
        sku_variant = normalize_sku(get("sku_variant"))
        sku_effective = sku_variant or sku_product
        return EcommChannelRow(
            ecomm_id=normalize_sku(get("ecomm_id")),
            sku=sku_effective,
            sku_product=sku_product,
            sku_variant=sku_variant,
            sku_effective=sku_effective,
            sku_source="sku_variant"
            if sku_variant
            else "sku_product"
            if sku_product
            else None,
            ean=normalize_ean(get("ean")),
            name=clean(get("name")),
            brand=clean(get("brand")),
            marketplace=clean(get("marketplace")),
            marketplace_id=normalize_sku(get("marketplace_id")),
            store=clean(get("store")),
            listing_id=normalize_sku(get("listing_id")),
            listing_title=clean(get("listing_title")),
            listing_status=clean(get("listing_status")),
            marketplace_price=normalize_decimal(get("price_marketplace")),
            list_price=normalize_decimal(get("price_list")),
            cost=normalize_decimal(get("cost")),
            stock=normalize_decimal(get("stock")),
            inventory_linked=clean(get("inventory_linked")),
        )

    def report_warnings(self, records):
        variant_count = sum(item.sku_source == "sku_variant" for item in records)
        fallback_count = sum(item.sku_source == "sku_product" for item in records)
        return [
            f"SKU efectivo: variante en {variant_count} filas; producto en {fallback_count} filas."
        ]
