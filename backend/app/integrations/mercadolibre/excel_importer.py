from ..common.excel import ExcelImporter
from ...catalog.models import ChannelListing
from ...catalog.normalizer import normalize_decimal, normalize_ean, normalize_sku

class MercadoLibreExcelImporter(ExcelImporter):
    source_label = "Mercado Libre"
    required_any = {"external_id", "sku", "ean"}
    aliases = {
      "external_id": {"ID publicación", "ID publicacion", "MLA", "ID"}, "sku": {"SKU", "Código SKU", "Codigo SKU", "Seller SKU"},
      "ean": {"EAN", "GTIN", "Código universal", "Codigo universal"}, "title": {"Título", "Titulo", "Publicación", "Producto"},
      "status": {"Estado", "Status"}, "price": {"Precio", "Price"}, "url": {"URL", "Link", "Permalink"}}
    def to_model(self, row, m):
        get=lambda key: row[m[key]] if key in m else None
        clean=lambda value: str(value).strip() if value is not None else None
        return ChannelListing(external_id=normalize_sku(get("external_id")), sku=normalize_sku(get("sku")), ean=normalize_ean(get("ean")), title=clean(get("title")), status=clean(get("status")), price=normalize_decimal(get("price")), url=clean(get("url")))
