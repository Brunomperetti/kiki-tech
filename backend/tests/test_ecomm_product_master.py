"""Full commercial product master is durable and never changes vendor catalog."""
import copy

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import Base, CatalogSnapshot
from app.services.ecomm_api_product_workspace_service import (
    EcommApiProductWorkspace, _canonical_fields, _readiness,
)


def snapshot():
    return [{
        "page": 1, "total": 1, "total_pages": 1, "per_page": 50,
        "captured_at": "2026-10-26T15:00:00+00:00",
        "items": [{
            "code": "X", "description": "Salsa de soja marca Sol",
            "variants": [{"id": 45, "sku": "SOJA-01", "is_combo": False,
                          "total_stock": 9, "gtin": None}],
        }],
    }]


def master():
    return {
        "brand": "Sol",
        "manufacturer": "Sol Alimentos",
        "title": "Salsa de soja Sol 500 ml",
        "short_title": "Salsa de soja Sol",
        "short_description": "Salsa de soja, presentación 500 ml.",
        "description": "Salsa de soja en botella de 500 ml, según etiqueta oficial.",
        "details": "Verificar rótulo antes de publicar.",
        "presentation": "Botella de 500 ml",
        "category": "Alimentos",
        "subcategory": "Salsas y aderezos",
        "seo_title": "Salsa de soja Sol 500 ml",
        "seo_description": "Salsa de soja Sol de 500 ml. Detalles de presentación confirmados.",
        "seo_keywords": "salsa de soja, 500 ml",
        "proposed_gtin": "",
        "note": "Rótulo verificado por responsable del catálogo.",
        "attributes": [{"name": "Contenido neto", "value": "500 ml"}],
        "media": [{"kind": "IMAGE", "url": "https://marca.example/soja-500.png",
                   "alt": "Etiqueta frontal", "source_url": "https://marca.example/soja"}],
        "sources": [{"kind": "FABRICANTE", "name": "Catálogo oficial Sol",
                     "url": "https://marca.example/soja",
                     "note": "Presentación corroborada en ficha fabricante"}],
    }


@pytest.fixture
def engine(tmp_path):
    dbengine = create_engine("sqlite:///" + str(tmp_path / "catalog.db"))
    Base.metadata.create_all(dbengine)
    with Session(dbengine) as db:
        db.add(CatalogSnapshot(source="ECOMM_APP_API_STAGE", payload=snapshot()))
        db.commit()
    yield dbengine
    dbengine.dispose()


def test_full_editor_commercial_media_evidence_and_seo_persist_between_sessions(engine):
    original = snapshot()
    with Session(engine) as db:
        saved = EcommApiProductWorkspace(db).save("45", master(), "READY_FOR_CHANNELS", 0)
        assert saved["readiness"]["ready"] is True
        assert saved["readiness"]["percent"] == 100
        assert saved["status"] == "READY_FOR_CHANNELS"
        assert saved["version"] == 1
        assert saved["fields"]["media"][0]["alt"] == "Etiqueta frontal"
        assert len(saved["history"]) == 1
    with Session(engine) as db:
        svc = EcommApiProductWorkspace(db)
        retrieved = svc.get("45")
        assert retrieved["fields"]["category"] == "Alimentos"
        assert retrieved["fields"]["subcategory"] == "Salsas y aderezos"
        assert retrieved["fields"]["seo_title"] == "Salsa de soja Sol 500 ml"
        assert retrieved["fields"]["attributes"][0]["value"] == "500 ml"
        assert retrieved["fields"]["sources"][0]["kind"] == "FABRICANTE"
        assert retrieved["readiness"]["ready"]
        assert svc.list_saved(status="READY_FOR_CHANNELS")["summary"]["ready_for_channels"] == 1
        assert db.scalar(select(CatalogSnapshot)).payload == original


def test_existing_five_field_drafts_migrate_without_losing_history(engine):
    with Session(engine) as db:
        svc = EcommApiProductWorkspace(db)
        legacy = {
            "brand": "Sol", "title": "Salsa de soja Sol",
            "description": "Pendiente de confirmar.", "proposed_gtin": "",
            "note": "Revisar contenido.",
        }
        before = svc.save("45", legacy, "DRAFT", 0)
        assert before["fields"]["media"] == []
        assert before["fields"]["category"] == ""
        assert before["history"][0]["changes"]["title"]["after"] == "Salsa de soja Sol"
        after = svc.save("45", master(), "READY_FOR_CHANNELS", 1)
        assert after["version"] == 2
        assert len(after["history"]) == 2
        assert after["history"][1]["changes"]["category"]["after"] == "Alimentos"
        assert after["history"][0]["changes"]["title"]["after"] == "Salsa de soja Sol"


def test_incomplete_full_record_stays_draft_or_review_not_ready(engine):
    with Session(engine) as db:
        svc = EcommApiProductWorkspace(db)
        pending = copy.deepcopy(master())
        pending["sources"] = []
        pending["media"] = []
        pending["category"] = ""
        with pytest.raises(ValueError, match="fuentes|fuente|faltan"):
            svc.save("45", pending, "READY_FOR_CHANNELS", 0)
        draft = svc.save("45", pending, "DRAFT", 0)
        assert not draft["readiness"]["ready"]
        assert "primary_source" in draft["readiness"]["missing"]
        assert "images" in draft["readiness"]["missing"]
        assert "category" in draft["readiness"]["missing"]


@pytest.mark.parametrize("key,value", [
    ("media", [{"kind": "IMAGE", "url": "javascript:alert(1)", "alt": "",
                "source_url": ""}]),
    ("media", [{"kind": "VIDEO", "url": "http://insecure.example/v", "alt": "",
                "source_url": ""}]),
    ("sources", [{"kind": "FABRICANTE", "name": "Supuesto fabricante",
                  "url": "http://unverified.example", "note": ""}]),
    ("attributes", [{"name": "Contenido", "value": ""}]),
])
def test_rejects_unsafe_media_sources_and_incomplete_attributes(key, value):
    payload = master()
    payload[key] = value
    with pytest.raises(ValueError):
        _canonical_fields(payload)


def test_unsaved_empty_new_rows_do_not_block_other_changes():
    payload = master()
    payload["media"].append({"kind": "IMAGE", "url": "", "alt": "", "source_url": ""})
    payload["sources"].append({"kind": "FABRICANTE", "name": "", "url": "", "note": ""})
    out = _canonical_fields(payload)
    assert len(out["media"]) == 1
    assert len(out["sources"]) == 1


def test_media_not_alone_sufficient_as_authoritative_evidence():
    payload = _canonical_fields(master())
    payload["sources"] = []
    ready = _readiness(payload)
    assert not ready["ready"]
    assert "primary_source" in ready["missing"]
