from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base, EnrichmentExternalResearch
from app.repositories.catalog_repository import CatalogRepository
from app.services.catalog_continuity_service import CatalogContinuityService


def product(*, brand=None, ean=None):
    return {
        "ecomm_id": "20",
        "sku": "A20",
        "sku_effective": "A20",
        "name": "Producto validado",
        "brand": brand,
        "ean": ean,
        "stock": 8,
        "price": 1000,
    }


def accepted_evidence(*, brand="Natufarma", ean="4006381333931", status="EVIDENCE_ACCEPTED"):
    return EnrichmentExternalResearch(
        product_key="ECOMM:20",
        reconciliation_run_id=1,
        status=status,
        proposed_brand=brand,
        proposed_ean=ean,
        source_name="Fabricante",
        source_url="https://example.com/producto",
        confidence="HIGH",
        product_snapshot=product(),
        internal_evidence={},
        history=[],
    )


def test_validated_kiki_data_survives_new_ecomm_snapshot_when_origin_is_empty():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        CatalogRepository(db).save_snapshot("ECOMM_APP", [product()])
        db.add(accepted_evidence())
        db.commit()

        service = CatalogContinuityService(db)
        report = service.report()
        effective = service.effective_index()["ECOMM:20"]

        assert report["summary"]["validated_products"] == 1
        assert report["summary"]["kiki_only"] == 2
        assert report["summary"]["conflicts"] == 0
        assert effective["brand"] == "Natufarma"
        assert effective["ean"] == "4006381333931"


def test_new_ecomm_conflict_is_blocked_until_human_decides():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        CatalogRepository(db).save_snapshot(
            "ECOMM_APP",
            [product(brand="Marca Ecomm", ean="4006381333931")],
        )
        db.add(accepted_evidence())
        db.commit()

        service = CatalogContinuityService(db)
        report = service.report()
        conflict = next(item for item in report["items"] if item["field"] == "brand")

        assert conflict["state"] == "CONFLICT"
        assert report["summary"]["conflicts"] == 1
        assert service.effective_index()["ECOMM:20"]["conflicts"][0]["field"] == "brand"


def test_human_can_keep_kiki_or_accept_ecomm_and_decision_becomes_stale_on_change():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        repo = CatalogRepository(db)
        repo.save_snapshot(
            "ECOMM_APP",
            [product(brand="Marca Ecomm", ean="4006381333931")],
        )
        db.add(accepted_evidence())
        db.commit()

        service = CatalogContinuityService(db)
        saved = service.save_decision("ECOMM:20:brand", "USE_KIKI")

        assert saved["state"] == "RESOLVED_USE_KIKI"
        assert service.effective_index()["ECOMM:20"]["brand"] == "Natufarma"

        repo.save_snapshot(
            "ECOMM_APP",
            [product(brand="Marca Nueva", ean="4006381333931")],
        )
        changed = next(
            item for item in service.report()["items"] if item["field"] == "brand"
        )
        assert changed["state"] == "STALE_DECISION"

        saved = service.save_decision("ECOMM:20:brand", "USE_ECOMM")
        assert saved["state"] == "RESOLVED_USE_ECOMM"
        assert service.effective_index()["ECOMM:20"]["brand"] == "Marca Nueva"


def test_gtin_exception_conflicts_if_new_ecomm_report_supplies_gtin():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        CatalogRepository(db).save_snapshot(
            "ECOMM_APP",
            [product(brand="Herboristeria", ean="4006381333931")],
        )
        db.add(
            accepted_evidence(
                brand="Herboristeria",
                ean=None,
                status="GTIN_NOT_APPLICABLE",
            )
        )
        db.commit()

        service = CatalogContinuityService(db)
        gtin = next(item for item in service.report()["items"] if item["field"] == "ean")

        assert gtin["state"] == "CONFLICT"
        assert gtin["kiki_exception"] is True

        service.save_decision("ECOMM:20:ean", "USE_ECOMM")
        effective = service.effective_index()["ECOMM:20"]
        assert effective["ean"] == "4006381333931"
        assert effective["gtin_exception"] is False
