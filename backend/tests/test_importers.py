from io import BytesIO
import pandas as pd
import pytest
from app.integrations.common.excel import ExcelImportError
from app.integrations.ecomm_app.excel_importer import EcommExcelImporter
from app.integrations.mercadolibre.excel_importer import MercadoLibreExcelImporter


def excel(frame, header=True):
    output = BytesIO()
    frame.to_excel(output, index=False, header=header, engine="openpyxl")
    return output.getvalue()


def test_alternative_headers_and_unknown_columns():
    report = EcommExcelImporter().read(
        excel(
            pd.DataFrame(
                [
                    {
                        "Código SKU": "001-A",
                        "Código de barra": "0779123456789",
                        "Producto": "Item",
                        "Precio": 10,
                        "Cantidad": 2,
                        "Extra": "x",
                    }
                ]
            )
        )
    )
    assert report.records[0].sku == "001-A" and report.records[0].ean == "0779123456789"
    assert report.unknown_columns == ["Extra"] and report.header_row == 1


def test_real_ecomm_headers_are_detected_after_information_row():
    rows = [
        ["No Modificar", "1", "Obligatorio", None, None, None, None, None, None, None],
        [
            "ID interno (no cambiar)",
            "Descripción del producto",
            "Marca",
            "Código de barra",
            "SKU del Producto",
            "SKU de la variante",
            "Precio Marketplace",
            "Precio Lista",
            "Costo del producto",
            "General",
        ],
        ["0007", "Café", "KIKI", None, "00100", "00100-RED", 120, 150, 60, 3],
        ["0008", "Té", "KIKI", "0779123456789", "00200", None, None, 90, 40, 0],
        [
            "Fila sin identificador",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ],
    ]
    report = EcommExcelImporter().read(excel(pd.DataFrame(rows), header=False))
    assert report.header_row == 2
    assert (report.rows_read, report.rows_accepted, report.rows_discarded) == (3, 2, 1)
    assert (
        report.records[0].sku_product,
        report.records[0].sku_variant,
        report.records[0].sku_effective,
        report.records[0].sku_source,
    ) == ("00100", "00100-RED", "00100-RED", "sku_variant")
    assert (
        report.records[1].sku_effective == "00200"
        and report.records[1].sku_source == "sku_product"
    )
    assert report.records[1].ean == "0779123456789"
    assert report.records[0].price == 120 and report.records[1].price == 90


def test_real_mercadolibre_aliases_and_inventory_link():
    frame = pd.DataFrame(
        [
            {
                "Título de la publicación": "Café",
                "Nro. de la publicación": "MLA001",
                "SKU": "00100",
                "SKU de la Variante": "00100-RED",
                "Status": "active",
                "Precio": 120,
                "Publicacion Vinculada con Inventario": "Sí",
            },
            {
                "Título de la publicación": "Té",
                "Nro. de la publicación": "MLA002",
                "SKU": "00200",
                "SKU de la Variante": None,
                "Status": "paused",
                "Precio": 90,
                "Publicacion Vinculada con Inventario": "No",
            },
        ]
    )
    report = MercadoLibreExcelImporter().read(excel(frame))
    assert (
        report.records[0].sku == "00100-RED"
        and report.records[0].variant_sku == "00100-RED"
        and report.records[0].inventory_linked == "Sí"
    )
    assert (
        report.records[1].status == "paused"
        and report.records[1].inventory_linked == "No"
    )


def test_invalid_file():
    with pytest.raises(ExcelImportError):
        EcommExcelImporter().read(b"not an excel")


def test_missing_minimum_headers():
    with pytest.raises(ExcelImportError, match="encabezados"):
        EcommExcelImporter().read(excel(pd.DataFrame([{"Nombre": "Item"}])))
