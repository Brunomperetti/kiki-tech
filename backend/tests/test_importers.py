from io import BytesIO
import pandas as pd
import pytest
from app.integrations.common.excel import ExcelImportError
from app.integrations.ecomm_app.excel_importer import EcommExcelImporter
def excel(frame):
 output=BytesIO();frame.to_excel(output,index=False,engine="openpyxl");return output.getvalue()
def test_alternative_headers_and_unknown_columns():
 report=EcommExcelImporter().read(excel(pd.DataFrame([{"Código SKU":"001-A","Código de barra":"0779123456789","Producto":"Item","Precio":10,"Cantidad":2,"Extra":"x"}])))
 assert report.records[0].sku=="001-A" and report.records[0].ean=="0779123456789" and report.unknown_columns==["Extra"]
def test_invalid_file():
 with pytest.raises(ExcelImportError): EcommExcelImporter().read(b"not an excel")
def test_missing_minimum_headers():
 with pytest.raises(ExcelImportError,match="columna válida"): EcommExcelImporter().read(excel(pd.DataFrame([{"Nombre":"Item"}])))
