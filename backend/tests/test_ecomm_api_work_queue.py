"""API-only queue triage, stable IDs, no provider writes, and meaningful pagination."""
from copy import deepcopy

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import Base, CatalogSnapshot, EcommApiProductEdit
from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
from app.services.ecomm_api_work_queue_service import build_queue
from test_ecomm_api_product_workspace import capture, payload


def db_fixture(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    engine = create_engine("sqlite:///" + str(tmp_path / "queue.db"))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(CatalogSnapshot(source="ECOMM_APP_API_STAGE", payload=capture()))
        db.add(CatalogSnapshot(source="ECOMM_APP", payload=[
            {"ecomm_id": "999", "sku": "invalid", "brand": "Excel brand"}
        ]))
        db.commit()
    return engine


def test_untouched_editorial_queue_sorted_and_read_only(tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        view = build_queue(db)
        assert view["source"] == "ECOMM_APP_API_STAGE"
        assert view["mode"] == "KIKI_INTERNAL_READ_ONLY_TRIAGE"
        assert view["summary"]["total"] == 2
        assert view["summary"]["untouched"] == 2
        assert view["summary"]["source_name_present"] == 2
        assert view["summary"]["source_name_missing"] == 0
        assert view["summary"]["missing_source_name"] == 0
        assert view["summary"]["editorial_started"] == 0
        assert view["summary"]["editorial_title_saved"] == 0
        # Source API names exist, so zero products should appear as "without title".
        assert all("missing_title" not in x["flags"] for x in view["items"])
        assert all("missing_brand" not in x["flags"] for x in view["items"])
        assert all("missing_description" not in x["flags"] for x in view["items"])
        assert view["summary"]["missing_brand"] == 0
        assert view["summary"]["missing_description"] == 0
        assert view["summary"]["missing_gtin"] == 0
        assert view["summary"]["pack"] == 1
        assert view["items"][0]["ecomm_id"] == "102"  # pack priority before simple
        assert view["items"][0]["is_combo"]
        assert view["external_writes_enabled"] is False
        assert not db.scalars(select(EcommApiProductEdit)).all()


def test_saved_draft_and_ready_status_filters_preserve_origins(tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        workspace = EcommApiProductWorkspace(db)
        workspace.save("102", payload(), "DRAFT", 0)
        workspace.save("101", payload(title="Simple confirmed"), "READY_FOR_REVIEW", 0)
        view = build_queue(db)
        assert view["summary"]["draft"] == 1
        assert view["summary"]["editorial_started"] == 2
        assert view["summary"]["editorial_brand_saved"] == 2
        assert view["summary"]["editorial_title_saved"] == 2
        assert view["summary"]["editorial_description_saved"] == 2
        assert view["summary"]["ready"] == 1
        assert view["summary"]["missing_brand"] == 0
        assert view["summary"]["missing_title"] == 0
        assert view["summary"]["missing_gtin"] == 2  # no invented GTIN
        assert view["items"][0]["ecomm_id"] == "102"
        assert build_queue(db, filter_name="draft")["items"][0]["ecomm_id"] == "102"
        assert build_queue(db, filter_name="ready")["items"][0]["ecomm_id"] == "101"
        assert build_queue(db, query="2500400")["total"] == 1
        assert build_queue(db, query="Vitamin")["total"] == 2
        assert build_queue(db, page=1, limit=1)["items"][0]["ecomm_id"] == "102"
        assert build_queue(db, page=2, limit=1)["items"][0]["ecomm_id"] == "101"
        assert db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        )).payload == capture()


def test_ambiguous_sku_and_changed_identity_get_priority(tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        workspace = EcommApiProductWorkspace(db)
        workspace.save("102", payload(), "DRAFT", 0)
        snapshot = db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        ))
        changed = deepcopy(snapshot.payload)
        changed[0]["items"][1]["variants"][0]["sku"] = "2500"
        snapshot.payload = changed
        db.commit()
        view = build_queue(db, filter_name="identity")
        assert view["total"] == 2
        assert all(item["priority"] == 0 for item in view["items"])
        assert all(item["identity_issue"] for item in view["items"])
        assert view["summary"]["identity"] == 2


def test_missing_or_incomplete_api_stage_blocks_queue(tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        stage = db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        ))
        db.delete(stage)
        db.commit()
        with pytest.raises(ValueError, match="incompleta"):
            build_queue(db)

    engine2 = db_fixture(tmp_path / "next")
    with Session(engine2) as db:
        stage = db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        ))
        wrong = deepcopy(stage.payload)
        wrong[0]["total_pages"] = 2
        stage.payload = wrong
        db.commit()
        with pytest.raises(ValueError, match="incompleta"):
            build_queue(db)


def test_unrecognized_filter_and_beyond_page_are_safe(tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        with pytest.raises(ValueError, match="Filtro"):
            build_queue(db, filter_name="export-ML")
        with pytest.raises(ValueError, match="paginación"):
            build_queue(db, page=0)
        final = build_queue(db, page=10, limit=1)
        assert final["total"] == 2 and final["items"] == []


def test_gtin_missing_from_api_is_not_treated_as_confirmed_missing_ean(tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        q = build_queue(db)
        assert q["gtin_data_quality"]["status"] == "NO_GTIN_EXPOSED_BY_CAPTURE"
        assert q["gtin_data_quality"]["gtin_unavailable_in_capture"] == 2
        assert q["gtin_data_quality"]["gtin_found_in_capture"] == 0
        assert q["items"][0]["gtin_source_state"] == "NOT_AVAILABLE_IN_API_CAPTURE"
        assert "NO" in q["gtin_data_quality"]["meaning"]

        stage = db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        ))
        changed = deepcopy(stage.payload)
        changed[0]["items"][0]["variants"][0]["barcode"] = "7791234567895"
        stage.payload = changed
        db.commit()
        updated = build_queue(db)
        assert updated["gtin_data_quality"]["gtin_found_in_capture"] == 1
        assert updated["gtin_data_quality"]["gtin_unavailable_in_capture"] == 1
        assert updated["gtin_data_quality"]["status"] == "PARTIAL_OR_COMPLETE_COVERAGE"
        assert updated["summary"]["missing_gtin"] == 0


def test_ai_eligible_filter_returns_only_simple_unique_api_variants(tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        summary = build_queue(db)
        assert summary["summary"]["ai_eligible"] == 1
        assert summary["summary"]["pack"] == 1
        eligible = build_queue(db, filter_name="ai_eligible")
        assert eligible["total"] == 1
        assert eligible["items"][0]["ecomm_id"] == "101"
        assert eligible["items"][0]["is_combo"] is False
        assert not eligible["items"][0]["identity_issue"]
        assert eligible["items"][0]["flags"].count("ai_eligible") == 1
        assert build_queue(db, filter_name="ai_eligible", query="2500400")["total"] == 0
        assert build_queue(db, filter_name="ai_eligible", page=2, limit=1)["items"] == []


def test_ai_eligible_rejects_identity_ambiguous_and_sku_drift(tmp_path):
    engine = db_fixture(tmp_path)
    with Session(engine) as db:
        saved = EcommApiProductWorkspace(db)
        saved.save("101", payload(), "DRAFT", 0)
        assert build_queue(db, filter_name="ai_eligible")["total"] == 1
        stage = db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        ))
        changed = deepcopy(stage.payload)
        changed[0]["items"][0]["variants"][0]["sku"] = "MODIFIED"
        stage.payload = changed
        db.commit()
        assert build_queue(db, filter_name="ai_eligible")["total"] == 0
        assert build_queue(db, filter_name="identity")["total"] == 1
        # A second API variant holding same SKU also blocks this filter.
        another = deepcopy(stage.payload)
        another[0]["items"][1]["variants"][0]["sku"] = "MODIFIED"
        stage.payload = another
        db.commit()
        assert build_queue(db, filter_name="ai_eligible")["total"] == 0
        assert build_queue(db)["summary"]["identity"] == 2


def test_started_editorial_gaps_do_not_count_untouched_api_products(tmp_path):
    engine=db_fixture(tmp_path)
    with Session(engine) as db:
        editor=EcommApiProductWorkspace(db)
        editor.save("101", {"note": "Falta revisar marca y textos."}, "DRAFT", 0)
        view=build_queue(db)
        assert view["summary"]["total"] == 2
        assert view["summary"]["untouched"] == 1
        assert view["summary"]["editorial_started"] == 1
        assert view["summary"]["missing_brand"] == 1
        assert view["summary"]["missing_title"] == 1
        assert view["summary"]["missing_description"] == 1
        assert view["summary"]["missing_gtin"] == 1
        assert view["summary"]["source_name_present"] == 2
        assert view["summary"]["missing_source_name"] == 0
        matched=build_queue(db,filter_name="missing_title")
        assert matched["total"] == 1
        assert matched["items"][0]["ecomm_id"] == "101"
        assert matched["items"][0]["product_name"].startswith("Magnesio")
        untouched=build_queue(db,filter_name="untouched")
        assert untouched["total"] == 1
        assert untouched["items"][0]["ecomm_id"] == "102"


def test_missing_source_name_is_real_gap_not_missing_optimized_title(tmp_path):
    engine=db_fixture(tmp_path)
    with Session(engine) as db:
        stage=db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source=="ECOMM_APP_API_STAGE"))
        changed=deepcopy(stage.payload)
        changed[0]["items"][0]["description"]=""
        stage.payload=changed
        db.commit()
        view=build_queue(db)
        assert view["summary"]["source_name_present"] == 1
        assert view["summary"]["source_name_missing"] == 1
        assert view["summary"]["missing_source_name"] == 1
        row=build_queue(db,filter_name="missing_source_name")["items"][0]
        assert row["ecomm_id"] == "101"
        assert row["priority"] == 1
        assert "verificar" in row["reason"]
        # No trustworthy name means no automated AI proposal.
        assert build_queue(db,filter_name="ai_eligible")["total"] == 0
        assert view["summary"]["missing_title"] == 0
