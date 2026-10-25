"""KIKI internal editing must survive DB sessions and never rewrite API snapshots."""
import copy
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import Base, CatalogSnapshot, EcommApiProductEdit
from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace


def capture():
    return [{
        "page": 1, "total": 2, "total_pages": 1, "per_page": 50,
        "captured_at": "2026-10-25T13:00:00+00:00",
        "items": [
            {"code": "2500", "description": "Magnesio con Potasio 30 cápsulas",
             "variants": [{"id": 101, "sku": "2500", "is_combo": False,
                           "total_stock": 12, "gtin": None}]},
            {"code": "2500_m", "description": "Pack x2 Magnesio con Potasio 60 cápsulas",
             "variants": [{"id": 102, "sku": "2500400", "is_combo": True,
                           "total_stock": 0, "gtin": None}]},
        ],
    }]


def payload(**overrides):
    return {
        "brand": "Vitamin Way",
        "title": "Magnesio con Potasio · Pack x2 · 60 cápsulas",
        "description": "Presentación pack x2, confirmar composición.",
        "proposed_gtin": "",
        "note": "Pendiente de corroborar rótulo.",
        **overrides,
    }


def setup(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "kiki.db"))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(CatalogSnapshot(source="ECOMM_APP_API_STAGE", payload=capture()))
        db.commit()
    return engine


def test_edits_persist_after_new_db_session_without_writing_capture(tmp_path):
    engine = setup(tmp_path)
    with Session(engine) as db:
        saved = EcommApiProductWorkspace(db).save("102", payload(), "DRAFT", 0)
        assert saved["version"] == 1
        assert saved["ecomm_id"] == "102"
        assert saved["source"]["is_combo"] is True
        assert saved["saved_in"] == "KIKI_POSTGRESQL_INTERNAL_ONLY"
        assert saved["external_writes_enabled"] is False

    with Session(engine) as db:
        svc = EcommApiProductWorkspace(db)
        retrieved = svc.get("102")
        assert retrieved["fields"]["brand"] == "Vitamin Way"
        assert retrieved["status"] == "DRAFT"
        assert len(retrieved["history"]) == 1
        assert db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        )).payload == capture()
        assert db.scalars(select(EcommApiProductEdit)).one().source_sku == "2500400"


def test_internal_review_and_history_are_auditable_and_isolated(tmp_path):
    engine = setup(tmp_path)
    with Session(engine) as db:
        svc = EcommApiProductWorkspace(db)
        svc.save("102", payload(), "DRAFT", 0)
        reviewed = svc.save("102", payload(note="Rótulo confirmado"), "READY_FOR_REVIEW", 1)
        assert reviewed["version"] == 2
        assert reviewed["status"] == "READY_FOR_REVIEW"
        assert reviewed["history"][1]["changes"]["note"]["before"] == "Pendiente de corroborar rótulo."
        assert reviewed["history"][1]["new_status"] == "READY_FOR_REVIEW"
        assert svc.get("101")["available"] is False
        assert svc.list_saved()["summary"]["ready_for_review"] == 1
        same = svc.save("102", payload(note="Rótulo confirmado"), "READY_FOR_REVIEW", 2)
        assert same["version"] == 2  # no duplicate audit event


def test_optimistic_lock_rejects_overwriting_someone_else_edits(tmp_path):
    engine = setup(tmp_path)
    with Session(engine) as db:
        svc = EcommApiProductWorkspace(db)
        svc.save("102", payload(), "DRAFT", 0)
        with pytest.raises(ValueError, match="otra sesión"):
            svc.save("102", payload(note="sobrescribir"), "DRAFT", 0)
        assert svc.get("102")["version"] == 1


def test_wrong_or_ambiguous_id_and_missing_api_snapshot_are_blocked(tmp_path):
    engine = setup(tmp_path)
    with Session(engine) as db:
        svc = EcommApiProductWorkspace(db)
        with pytest.raises(ValueError, match="única variante"):
            svc.save("9999", payload(), "DRAFT", 0)
        with pytest.raises(ValueError, match="al menos"):
            svc.save("102", payload(brand="",title="",description="",note=""), "DRAFT", 0)
        with pytest.raises(ValueError, match="GTIN"):
            svc.save("102", payload(proposed_gtin="7790000000000"), "DRAFT", 0)
        assert db.scalars(select(EcommApiProductEdit)).all() == []
    with Session(engine) as db:
        stage = db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        ))
        changed = copy.deepcopy(stage.payload)
        changed[0]["total_pages"] = 2
        stage.payload = changed
        db.commit()
        with pytest.raises(ValueError, match="copia API"):
            EcommApiProductWorkspace(db).get("102")


def test_stable_id_draft_survives_stock_change_but_blocks_sku_identity_swap(tmp_path):
    engine = setup(tmp_path)
    with Session(engine) as db:
        svc = EcommApiProductWorkspace(db)
        svc.save("102", payload(), "DRAFT", 0)
        stage = db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        ))
        changed = copy.deepcopy(stage.payload)
        changed[0]["items"][1]["variants"][0]["total_stock"] = 33
        stage.payload = changed
        db.commit()
        read = svc.get("102")
        assert read["source"]["stock_at_capture"] == 33
        assert not read["source_sku_changed"]
        changed2 = copy.deepcopy(stage.payload)
        changed2[0]["items"][1]["variants"][0]["sku"] = "2500999"
        stage.payload = changed2
        db.commit()
        assert svc.get("102")["source_sku_changed"] is True
        with pytest.raises(ValueError, match="SKU"):
            svc.save("102", payload(note="manual"), "DRAFT", 1)
        assert svc.get("102")["version"] == 1


def test_saved_list_filters_without_merging_variants(tmp_path):
    engine = setup(tmp_path)
    with Session(engine) as db:
        svc = EcommApiProductWorkspace(db)
        svc.save("101", payload(brand="Base"), "DRAFT", 0)
        svc.save("102", payload(brand="Pack"), "READY_FOR_REVIEW", 0)
        out = svc.list_saved(query="2500400", status="READY_FOR_REVIEW")
        assert out["total"] == 1 and out["items"][0]["ecomm_id"] == "102"
        assert out["summary"]["total_saved"] == 2
        assert out["summary"]["drafts"] == 1
