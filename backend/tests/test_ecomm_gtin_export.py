"""Tests for bounded, provenance-preserving Ecomm-App export GTIN ingestion."""
from io import BytesIO

import pytest
from openpyxl import Workbook

from app.services.ecomm_gtin_export_service import (
    _read_xlsx, _match_export, _prepare, MAX_BYTES,
)


def export_bytes(rows=None, *, header="gtin"):
    book = Workbook()
    sheet = book.active
    sheet.title = "Actualización de productos"
    sheet.append([
        "id_interno", "descripcion", "descripcion_variante", "sku_madre",
        "sku", "precio_compra", "costo_incluye_iva", "precio_venta",
        "alicuota_iva", "precio_incluye_iva", "stock_1", "stock_2",
        "stock_3", header,
    ])
    sheet.append(["ID interno", "Descripción", "Descripción variante", "SKU madre",
                  "SKU", None, None, None, None, None, None, None, None, "GTIN"])
    for row in rows or [(8021010, "100000100", "7798353193212")]:
        sheet.append([row[0], "Producto", "Presentación", "Madre", row[1],
                      None, None, None, None, None, None, None, None, row[2]])
    result = BytesIO()
    book.save(result)
    book.close()
    return result.getvalue()


def stage():
    return {"8021010": {"sku": "100000100", "combo": False, "api_gtin": ""},
            "8200172": {"sku": "100000999", "combo": False, "api_gtin": ""}}


def test_import_exact_ids_sku_and_gtin():
    rows = _read_xlsx(export_bytes([(8021010, "100000100", "7798353193212"),
                                    (8200172, "100000999", "7798353193212")]))
    assert len(rows) == 2
    _match_export(rows, stage())
    output, counts = _prepare(rows, stage())
    assert counts["VALID_REPEATED"] == 2
    assert output[0]["ecomm_id"] == "8021010"


def test_numeric_id_does_not_become_scientific_notation():
    rows = _read_xlsx(export_bytes())
    assert rows["8021010"]["ecomm_id"] == "8021010"


def test_missing_variant_rejected():
    with pytest.raises(ValueError, match="faltan"):
        _match_export(_read_xlsx(export_bytes()), stage())


def test_different_sku_rejected():
    with pytest.raises(ValueError, match="SKU"):
        _match_export(_read_xlsx(export_bytes([
            (8021010, "999999", "7798353193212"),
            (8200172, "100000999", "7798353193212"),
        ])), stage())


def test_duplicate_id_rejected():
    with pytest.raises(ValueError, match="duplicados"):
        _read_xlsx(export_bytes([
            (8021010, "100000100", "7798353193212"),
            (8021010, "100000100", "7798353193212"),
        ]))


def test_invalid_gtin_never_considered_verified():
    s = {"8021010": stage()["8021010"]}
    items = _read_xlsx(export_bytes([(8021010, "100000100", "3")]))
    _, counts = _prepare(items, s)
    assert counts["INVALID"] == 1


def test_pack_never_auto_approved_even_unique_valid_gtin():
    s = {"8021010": {**stage()["8021010"], "combo": True}}
    items = _read_xlsx(export_bytes())
    _, counts = _prepare(items, s)
    assert counts["PACK_REVIEW"] == 1


def test_structure_must_match_ecomm_export():
    with pytest.raises(ValueError, match="estructura"):
        _read_xlsx(export_bytes(header="codigo_inventado"))


def test_reject_oversized_files():
    with pytest.raises(ValueError, match="3 MB"):
        _read_xlsx(b"x" * (MAX_BYTES + 1))


def test_no_missing_gtin_promoted():
    s = {"8021010": stage()["8021010"]}
    rows = _read_xlsx(export_bytes([(8021010, "100000100", None)]))
    assert _prepare(rows, s)[1]["MISSING"] == 1
