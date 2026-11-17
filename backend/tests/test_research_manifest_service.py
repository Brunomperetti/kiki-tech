"""Read-only manufacturer research worklist: no invented EAN, claim or source."""
import csv
from copy import deepcopy
from io import StringIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import CatalogSnapshot, EcommApiProductEdit
from app.services.research_manifest_service import (
    MAX_ROWS, HEADER, _cell, build_research_manifest,
)
from test_ecomm_api_work_queue import db_fixture


def eligible(db):
    stage = db.scalar(select(CatalogSnapshot).where(
        CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
    ))
    pages = deepcopy(stage.payload)
    pages[0]["items"][0]["variants"][0]["variant_description"] = "30 cápsulas"
    pages[0]["items"][0]["variants"][0]["barcode"] = "7798353193212"
    pages[0]["items"][1]["variants"][0]["barcode"] = "8410771100656"
    pages[0]["items"][1]["variants"][0]["variant_description"] = "Pack x2 60 cápsulas"
    stage.payload = pages
    export = CatalogSnapshot(source="ECOMM_APP_GTIN_EXPORT", payload=[{
        "version": 1, "variants": 2, "rows": [
            {"ecomm_id": "101", "sku": "2500", "gtin": "7798353193212",
             "status": "VALID_UNIQUE", "is_combo": False},
            {"ecomm_id": "102", "sku": "2500400", "gtin": "8410771100656",
             "status": "PACK_REVIEW", "is_combo": True},
        ],
    }])
    db.add(export)
    db.commit()
    return stage, export


def parse(body):
    assert body.startswith("\ufeff")
    return list(csv.reader(StringIO(body[1:])))


def test_research_manifest_has_sourced_identity_not_fabricated_manufacturer(tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        stage, _ = eligible(db)
        before = deepcopy(stage.payload)
        body, count = build_research_manifest(db)
        rows = parse(body)
        assert count == 1
        assert tuple(rows[0]) == HEADER
        assert len(rows) == 2
        product = dict(zip(HEADER, rows[1]))
        assert product["ecomm_id"] == "101"
        assert product["sku"] == "2500"
        assert product["barcode_api_solo_busqueda"] == "7798353193212"
        assert product["estado_fuente"] == "PENDIENTE_VERIFICACION_FABRICANTE"
        assert "7798353193212" in product["busqueda_sugerida"]
        assert product["url_fabricante"] == product["cita_fuente"] == ""
        assert product["fecha_verificacion"] == ""
        assert "102" not in [row[0] for row in rows[1:]]
        assert db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        )).payload == before
        assert db.scalars(select(EcommApiProductEdit)).all() == []


def test_historic_export_cannot_change_api_research_candidates(tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        stage, export = eligible(db)
        # Even a tampered old Excel cannot change the API-only manifest.
        export.payload = [{
            **export.payload[0],
            "rows": [
                {**export.payload[0]["rows"][0], "sku": "changed",
                 "gtin": "0000000000000"},
                {**export.payload[0]["rows"][1], "gtin": "0000000000000",
                 "status": "VALID_UNIQUE"},
            ],
        }]
        db.commit()
        body, count = build_research_manifest(db)
        assert count == 1 and len(parse(body)) == 2
        assert "7798353193212" in body
        assert "0000000000000" not in body

        pages = deepcopy(stage.payload)
        pages[0]["items"][0]["variants"][0]["barcode"] = "3"
        stage.payload = pages
        db.commit()
        body, count = build_research_manifest(db)
        assert count == 0 and len(parse(body)) == 1

        pages = deepcopy(stage.payload)
        pages[0]["items"][0]["variants"][0]["barcode"] = "7798353193212"
        pages[0]["items"][0]["variants"][0].pop("variant_description")
        stage.payload = pages
        db.commit()
        body, count = build_research_manifest(db)
        assert count == 0 and len(parse(body)) == 1


def test_formula_injection_not_interpreted_as_spreadsheet_formula():
    assert _cell("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert _cell("  @evil") == "'@evil"
    assert _cell("text\nline") == "text line"
    assert MAX_ROWS == 5000
