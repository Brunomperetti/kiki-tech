"""Source-backed channel coverage for every Ecomm API variant, with fail-closed matching."""
from copy import deepcopy

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import Base, CatalogSnapshot, EcommApiProductEdit
from app.services.ecomm_channel_coverage_service import build_channel_coverage
from app.services.ecomm_api_work_queue_service import build_queue
from test_ecomm_api_product_workspace import payload


def sample():
    return [{
        "page": 1, "total": 7, "total_pages": 1, "per_page": 50,
        "captured_at": "2026-10-26T09:30:00+00:00",
        "items": [
            {"code": "M", "description": "Aceite de oliva Sol 500 ml", "variants": [
                {"id": 1, "sku": "OIL", "total_stock": 4, "is_combo": False}
            ]},
            {"code": "B", "description": "Pack x2 Magnesio 30 capsulas", "variants": [
                {"id": 2, "sku": "PACK", "is_combo": True}
            ]},
            {"code": "C", "description": "Chocolate 200 g", "variants": [
                {"id": 3, "sku": "DUP", "is_combo": False}
            ]},
            {"code": "D", "description": "Chocolate 500 g", "variants": [
                {"id": 4, "sku": "DUP", "is_combo": False}
            ]},
            {"code": "E", "description": "Yerba mate 500 g", "variants": [
                {"id": 5, "sku": "VAR", "is_combo": False}
            ]},
            {"code": "F", "description": "Jabon neutro 100 g", "variants": [
                {"id": 6, "sku": "CHANGE", "is_combo": False}
            ]},
            {"code": "G", "description": "Crema corporal 200 ml", "variants": [
                {"id": 7, "sku": "ABSENT", "is_combo": False}
            ]},
        ]
    }]


def ml(eid, sku, title, *, variant_sku=None):
    return {"external_id": eid, "sku": sku, "sku_effective": sku,
            "sku_product": sku, "variant_sku": variant_sku, "title": title,
            "status": "active", "price": "111"}


def tn(sku, name, slug=None, description=True):
    return {"sku": sku, "name": name, "slug": slug or sku,
            "brand": "Marca", "description_present": description,
            "ean_raw": "", "stock": "2", "price": "123"}


def db_fixture(tmp_path, *, ml_rows=None, tn_rows=None):
    engine = create_engine("sqlite:///" + str(tmp_path / "coverage.db"))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(CatalogSnapshot(source="ECOMM_APP_API_STAGE", payload=sample()))
        if ml_rows is not None:
            db.add(CatalogSnapshot(source="MERCADOLIBRE_API", payload=ml_rows))
        if tn_rows is not None:
            db.add(CatalogSnapshot(source="TIENDANUBE", payload=tn_rows))
        # Poisoned old source must never affect current cross-channel results.
        db.add(CatalogSnapshot(source="ECOMM_APP", payload=[
            {"ecomm_id": "POISON", "sku": "ABSENT", "ean": "7791234567895"}
        ]))
        db.add(CatalogSnapshot(source="MERCADOLIBRE", payload=[
            ml("MLAOLD", "ABSENT", "old Excel")
        ]))
        db.commit()
    return engine


def test_channel_matrix_never_promotes_sku_match_to_verified_linkage(tmp_path):
    mls=[
        ml("MLA1", "OIL", "Aceite de oliva Sol 500 ml"),
        ml("MLA2", "PACK", "Pack x2 Magnesio 30 capsulas"),
        ml("MLA3", "DUP", "Chocolate 200 g"),
        # Inherited product SKU is not evidence of an actual ML variation.
        ml("MLA4#123", "VAR", "Yerba mate 500 g"),
        ml("MLA5", "CHANGE", "Jabon neutro 250 g"),
    ]
    tns=[
        tn("OIL", "Aceite de oliva Sol 500 ml"),
        tn("PACK", "Pack x2 Magnesio 30 capsulas"),
        tn("DUP", "Chocolate 200 g"),
        tn("CHANGE", "Jabon neutro 250 g"),
        tn("VAR", "Yerba mate 500 g"),
    ]
    engine=db_fixture(tmp_path,ml_rows=mls,tn_rows=tns)
    with Session(engine) as db:
        before=deepcopy(db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source=="ECOMM_APP_API_STAGE")).payload)
        m=build_channel_coverage(db,before)
        a=m["items_by_id"]
        assert m["summary"]["api_variants"] == 7
        assert a["1"]["ml"]["status"] == "SKU_CANDIDATE"
        assert a["1"]["tn"]["status"] == "SKU_CANDIDATE"
        assert a["1"]["combined"] == "BOTH_CHANNELS_CANDIDATE"
        assert not a["1"]["ml"]["confirmed_listing"]
        assert not a["1"]["tn"]["confirmed_listing"]
        assert a["2"]["ml"]["status"] == "PACK_REVIEW"
        assert a["2"]["tn"]["status"] == "PACK_REVIEW"
        assert a["3"]["ml"]["status"] == "AMBIGUOUS_API_SKU"
        assert a["4"]["tn"]["status"] == "AMBIGUOUS_API_SKU"
        assert a["5"]["ml"]["status"] == "NO_EXACT_SKU_IN_SNAPSHOT"
        assert a["5"]["tn"]["status"] == "SKU_CANDIDATE"
        assert m["summary"]["ml_rows_unmatchable_variation_sku"] == 1
        assert a["6"]["ml"]["status"] == "PRESENTATION_CONFLICT"
        assert a["6"]["tn"]["status"] == "PRESENTATION_CONFLICT"
        assert a["7"]["ml"]["status"] == "NO_EXACT_SKU_IN_SNAPSHOT"
        assert a["7"]["tn"]["status"] == "NO_EXACT_SKU_IN_SNAPSHOT"
        assert a["7"]["combined"] == "NO_EXACT_EVIDENCE_IN_BOTH_SNAPSHOTS"
        assert db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source=="ECOMM_APP_API_STAGE")).payload == before
        assert db.scalars(select(EcommApiProductEdit)).all() == []


def test_multiple_channel_rows_do_not_trigger_any_auto_deduplication(tmp_path):
    engine=db_fixture(tmp_path,ml_rows=[
        ml("MLA1", "OIL", "Aceite de oliva Sol 500 ml"),
        ml("MLA2", "OIL", "Aceite de oliva Sol 500 ml"),
    ],tn_rows=[
        tn("OIL", "Aceite de oliva Sol 500 ml", "a"),
        tn("OIL", "Aceite de oliva Sol 500 ml", "b"),
    ])
    with Session(engine) as db:
        a=build_channel_coverage(db,sample())["items_by_id"]["1"]
        assert a["ml"]["status"] == "MULTIPLE_SKU_ROWS"
        assert a["tn"]["status"] == "MULTIPLE_SKU_ROWS"
        assert a["ml"]["matching_rows"] == 2
        assert a["tn"]["matching_rows"] == 2
        assert a["combined"] == "IDENTITY_REVIEW"
        assert a["ml"]["listing_ids"] == ["MLA1", "MLA2"]


def test_unavailable_snapshots_never_claim_absence_or_publication(tmp_path):
    engine=db_fixture(tmp_path)
    with Session(engine) as db:
        result=build_channel_coverage(db,sample())
        a=result["items_by_id"]["1"]
        assert a["ml"]["status"] == "UNAVAILABLE"
        assert a["tn"]["status"] == "UNAVAILABLE"
        assert a["combined"] == "SOURCES_UNAVAILABLE"
        assert result["sources"]["ml"]["available"] is False
        assert result["sources"]["tn"]["available"] is False
        assert result["summary"]["combined"]["SOURCES_UNAVAILABLE"] == 5
        assert a["ml"]["confirmed_listing"] is False


def test_queue_uses_channel_evidence_and_started_only_incomplete(tmp_path):
    engine=db_fixture(tmp_path,ml_rows=[
        ml("MLA1", "OIL", "Aceite de oliva Sol 500 ml"),
        ml("MLA2", "PACK", "Pack x2 Magnesio 30 capsulas"),
    ],tn_rows=[
        tn("OIL", "Aceite de oliva Sol 500 ml"),
        tn("PACK", "Pack x2 Magnesio 30 capsulas"),
    ])
    with Session(engine) as db:
        queue=build_queue(db)
        assert queue["summary"]["total"] == 7
        assert queue["summary"]["untouched"] == 7
        assert queue["summary"]["needs_completion"] == 0
        assert queue["summary"]["ml_candidate"] == 1
        assert queue["summary"]["tn_candidate"] == 1
        assert queue["summary"]["both_candidates"] == 1
        assert queue["summary"]["channel_review"] >= 1
        assert queue["channel_coverage"]["sources"]["ml"]["rows"] == 2
        all_both=build_queue(db,filter_name="both_candidates")
        assert all_both["total"] == 1
        assert all_both["items"][0]["ecomm_id"] == "1"
        review=build_queue(db,filter_name="channel_review")
        assert review["total"] >= 1
        assert any(row["ecomm_id"]=="2" for row in review["items"])
