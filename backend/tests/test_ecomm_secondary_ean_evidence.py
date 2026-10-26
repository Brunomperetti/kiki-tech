"""Historical Excel EAN is evidence only; catalog identity is Ecomm API."""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base
from app.repositories.catalog_repository import CatalogRepository
from app.services.ecomm_secondary_ean_evidence import EcommLegacyEanEvidence


VALID = "7791234567898"


def variant(ident, sku, is_combo=False, gtin=None):
    return {"id": ident, "sku": sku, "is_combo": is_combo,
            "total_stock": 4, "gtin": gtin, "barcode": None}


def parent(label, *variants):
    return {"code": "FAMILY", "description": label, "is_combo": False,
            "variants": list(variants)}


def write_snapshot(db, products, historical):
    repo=CatalogRepository(db)
    repo.save_snapshot("ECOMM_APP_API_STAGE", [{
        "version": 1, "page": 1, "total": len(products), "total_pages": 1,
        "per_page": 50, "captured_at": "2026-10-26T12:00:00+00:00", "items": products,
    }])
    repo.save_snapshot("ECOMM_APP_RAW", historical)


def old(sku, ean=VALID, name="Salsa de soja"):
    return {
        "ecomm_id": "LEGACY_PARENT", "sku": sku, "sku_effective": sku,
        "sku_variant": sku, "sku_product": "FAMILY", "ean": ean,
        "name": name, "list_price": "200", "stock": "1000",
    }


def test_secondary_ean_suggests_only_unique_exact_sku_and_preserves_source():
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        write_snapshot(db,[parent("Salsa de soja",variant("API-1","SKU-1"))],[old("SKU-1")])
        service=EcommLegacyEanEvidence(db)
        evidence=service.get("API-1")
        assert evidence["status"] == "CANDIDATE"
        assert evidence["candidate_ean"] == VALID
        assert evidence["api_source"] == "ECOMM_APP_API_STAGE"
        assert evidence["evidence_source"] == "ECOMM_APP_RAW_XLSX_HISTORICAL"
        assert evidence["can_use"] is True
        assert evidence["kiki_saved_gtin"] == ""
        assert service.summary()["possible_candidates"] == 1
        assert db.get(__import__("app.database.models",fromlist=["EcommApiProductEdit"]).EcommApiProductEdit, "API-1") is None
        assert CatalogRepository(db).snapshot("ECOMM_APP_API_STAGE")[0]["items"][0]["variants"][0]["gtin"] is None


def test_repeated_api_sku_is_blocked_even_if_one_ean_looks_correct():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine)
    with Session(engine) as db:
        write_snapshot(db,[parent("A",variant("API-1","DUP"),variant("API-2","DUP"))],[old("DUP")])
        result=EcommLegacyEanEvidence(db).get("API-1")
        assert result["status"] == "AMBIGUOUS_API_SKU"
        assert result["candidate_ean"] is None


def test_family_only_sku_and_pack_cannot_inherit_ean():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine)
    with Session(engine) as db:
        write_snapshot(db,[
            parent("Producto",variant("API-1","SKU-1"),variant("API-2","SKU-2")),
            parent("Combo",variant("API-3","PACK",is_combo=True)),
        ],[
            {"sku_effective":"SKU-1","sku_variant":"","sku_product":"SKU-1","ean":VALID},
            old("PACK"),
        ])
        service=EcommLegacyEanEvidence(db)
        assert service.get("API-1")["status"] == "AMBIGUOUS_LEGACY_SKU"
        assert service.get("API-3")["status"] == "PACK_REVIEW_REQUIRED"


def test_conflict_invalid_ean_and_different_legacy_names_are_blocked():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine)
    with Session(engine) as db:
        write_snapshot(db,[parent("Producto",variant("API-1","SKU-1"))],
                       [old("SKU-1"),old("SKU-1","7791234567881")])
        svc=EcommLegacyEanEvidence(db)
        assert svc.get("API-1")["status"] == "CONFLICTING_OR_MISSING_EAN"
        CatalogRepository(db).save_snapshot("ECOMM_APP_RAW",[old("SKU-1","7791234567890")])
        assert svc.get("API-1")["status"] == "INVALID_EAN"
        CatalogRepository(db).save_snapshot("ECOMM_APP_RAW",[old("SKU-1"),old("SKU-1",name="Otra presentación")])
        assert svc.get("API-1")["status"] == "AMBIGUOUS_LEGACY_SKU"


def test_existing_api_gtin_takes_precedence():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine)
    with Session(engine) as db:
        write_snapshot(db,[parent("Producto",variant("API-1","SKU-1",gtin="7791234567881"))],[old("SKU-1")])
        result=EcommLegacyEanEvidence(db).get("API-1")
        assert result["status"] == "API_HAS_GTIN"
        assert result["candidate_ean"] is None


def test_no_raw_snapshot_does_not_guess_an_ean():
    engine=create_engine("sqlite://");Base.metadata.create_all(engine)
    with Session(engine) as db:
        CatalogRepository(db).save_snapshot("ECOMM_APP_API_STAGE",[{
            "version":1,"page":1,"total":1,"total_pages":1,"per_page":50,
            "captured_at":"2026-10-26T12:00:00+00:00",
            "items":[parent("Producto",variant("API-1","SKU-1"))],
        }])
        result=EcommLegacyEanEvidence(db).get("API-1")
        assert result["status"] == "NO_LEGACY_SOURCE"
        assert not result["can_use"]
