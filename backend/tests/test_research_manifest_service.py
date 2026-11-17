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
        assert product["gtin_excel_solo_busqueda"] == "7798353193212"
        assert product["estado_fuente"] == "PENDIENTE_VERIFICACION_FABRICANTE"
        assert "7798353193212" in product["busqueda_sugerida"]
        assert product["url_fabricante"] == product["cita_fuente"] == ""
        assert product["fecha_verificacion"] == ""
        assert "102" not in [row[0] for row in rows[1:]]
        assert db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        )).payload == before
        assert db.scalars(select(EcommApiProductEdit)).all() == []


def test_research_manifest_fails_closed_when_export_is_stale_or_repeated(tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        stage, export = eligible(db)
        export.payload = [{
            **export.payload[0],
            "rows": [{**export.payload[0]["rows"][0], "sku": "changed"},
                     export.payload[0]["rows"][1]],
        }]
        db.commit()
        body, count = build_research_manifest(db)
        assert count == 0
        assert len(parse(body)) == 1
        # Do not expose a conflicting unique GTIN even with a forged status.
        stale = deepcopy(export.payload)
        stale[0]["rows"][0]["sku"] = "2500"
        stale[0]["rows"][1]["gtin"] = stale[0]["rows"][0]["gtin"]
        stale[0]["rows"][1]["status"] = "VALID_UNIQUE"
        export.payload = stale
        db.commit()
        body, count = build_research_manifest(db)
        assert count == 0
        assert len(parse(body)) == 1
        # Lack of presentation also excludes candidate.
        stale = deepcopy(export.payload)
        stale[0]["rows"][1]["gtin"] = "8410771100656"
        stale[0]["rows"][1]["status"] = "PACK_REVIEW"
        export.payload = stale
        pages = deepcopy(stage.payload)
        pages[0]["items"][0]["variants"][0].pop("variant_description")
        stage.payload = pages
        db.commit()
        body, count = build_research_manifest(db)
        assert count == 0
        assert len(parse(body)) == 1


def test_formula_injection_not_interpreted_as_spreadsheet_formula():
    assert _cell("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert _cell("  @evil") == "'@evil"
    assert _cell("text\nline") == "text line"
    assert MAX_ROWS == 5000
