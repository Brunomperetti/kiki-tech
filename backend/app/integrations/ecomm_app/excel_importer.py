from ..common.excel import ExcelImporter
from ...catalog.models import Product
from ...catalog.normalizer import normalize_decimal, normalize_ean, normalize_sku

class EcommExcelImporter(ExcelImporter):
    source_label = "Ecomm-App"
    required_any = {"sku", "ean"}
    aliases = {
      "ecomm_id": {"ID", "ID producto", "Código interno"}, "sku": {"SKU", "SKU producto", "Código SKU", "Codigo SKU"},
      "ean": {"EAN", "GTIN", "Código de barra", "Codigo de barras", "Barcode"}, "name": {"Nombre", "Producto", "Descripción", "Descripcion"},
      "brand": {"Marca", "Brand"}, "price": {"Precio", "Precio venta"}, "cost": {"Costo", "Cost"}, "stock": {"Stock", "Inventario", "Cantidad"}}
    def to_model(self, row, m):
        get=lambda key: row[m[key]] if key in m else None
        return Product(ecomm_id=normalize_sku(get("ecomm_id")), sku=normalize_sku(get("sku")), ean=normalize_ean(get("ean")), name=str(get("name")).strip() if get("name") is not None else None, brand=str(get("brand")).strip() if get("brand") is not None else None, price=normalize_decimal(get("price")), cost=normalize_decimal(get("cost")), stock=normalize_decimal(get("stock")))
