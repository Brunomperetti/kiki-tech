from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base, EnrichmentExternalResearch
from app.services.prepublication_service import PrepublicationService


def readiness_item(*, ecomm_id, sku, name, stock=5, brand=None, ean=None, status="READY_CORE_DATA"):
    return {
        "product": {
            "ecomm_id": ecomm_id,
            "sku": sku,
            "name": name,
            "stock": stock,
            "price": 1000,
            "brand": brand,
            "ean": ean,
        },
        "readiness_status": status,
        "reason_codes": [],
    }


def test_prepublication_includes_core_ready_and_accepted_evidence_only():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(
            EnrichmentExternalResearch(
                product_key="ECOMM:20",
                reconciliation_run_id=1,
                status="EVIDENCE_ACCEPTED",
                proposed_brand="Natufarma",
                proposed_ean="7795379101108",
                source_name="Fabricante",
                source_url="https://example.com/producto",
                confidence="HIGH",
                product_snapshot={},
                internal_evidence={},
                history=[],
            )
        )
        db.commit()

        service = PrepublicationService(db)
        service.readiness.report = lambda: {
            "items": [
                readiness_item(
                    ecomm_id="10",
                    sku="A10",
                    name="Producto listo",
                    brand="Marca",
                    ean="7790000000001",
                ),
                readiness_item(
                    ecomm_id="20",
                    sku="A20",
                    name="Valeriana Natufarma",
                    brand=None,
                    ean=None,
                    status="REVIEW_REQUIRED",
                ),
                readiness_item(
                    ecomm_id="30",
                    sku="A30",
                    name="Todavía pendiente",
                    status="REVIEW_REQUIRED",
                ),
                readiness_item(
                    ecomm_id="40",
                    sku="A40",
                    name="Sin stock",
                    stock=0,
                    status="NO_STOCK",
                ),
            ]
        }

        report = service.report()

        assert report["summary"]["total"] == 2
        assert report["summary"]["from_ecomm_core"] == 1
        assert report["summary"]["from_accepted_evidence"] == 1
        accepted = next(item for item in report["items"] if item["product_key"] == "ECOMM:20")
        assert accepted["verified_core_data"]["brand"] == "Natufarma"
        assert accepted["verified_core_data"]["ean"] == "7795379101108"
        assert accepted["checks"]["images"] == "WAITING_IMAGE_DATA"
        assert accepted["checks"]["category"] == "WAITING_ML_CONNECTION"
        assert accepted["checks"]["preview"] == "BLOCKED"


def test_prepublication_never_overwrites_existing_catalog_values_with_evidence():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(
            EnrichmentExternalResearch(
                product_key="ECOMM:20",
                reconciliation_run_id=1,
                status="EVIDENCE_ACCEPTED",
                proposed_brand="Otra Marca",
                proposed_ean="7795379101108",
                source_name="Fuente",
                source_url="https://example.com/producto",
                confidence="HIGH",
                product_snapshot={},
                internal_evidence={},
                history=[],
            )
        )
        db.commit()

        service = PrepublicationService(db)
        service.readiness.report = lambda: {
            "items": [
                readiness_item(
                    ecomm_id="20",
                    sku="A20",
                    name="Producto",
                    brand="Marca Ecomm",
                    ean=None,
                    status="REVIEW_REQUIRED",
                )
            ]
        }

        report = service.report()
        item = report["items"][0]
        assert item["verified_core_data"]["brand"] == "Marca Ecomm"
        assert item["verified_core_data"]["ean"] == "7795379101108"
