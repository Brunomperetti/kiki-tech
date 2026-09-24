from app.catalog.normalizer import normalize_ean,normalize_sku,normalize_title
def test_normalize_sku_preserves_leading_zeroes(): assert normalize_sku(" 001-ab ")=="001-AB"
def test_normalize_numeric_excel_identifier(): assert normalize_sku(123.0)=="123"
def test_normalize_ean(): assert normalize_ean(" 0779-1234 5678-9 ")=="0779123456789"
def test_normalize_title(): assert normalize_title("  Café -- MOLIDO  ")=="CAFE MOLIDO"
