import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base, PrepublicationImageReview
from app.services.prepublication_image_service import PrepublicationImageService
from app.services.prepublication_service import PrepublicationService


def prepublication_item():
    return {
        "product_key": "ECOMM:20",
        "product": {
            "ecomm_id": "20",
            "sku": "A20",
            "name": "Valeriana Natufarma x 40",
            "stock": 12,
            "brand": "Natufarma",
            "ean": "7795379101108",
        },
        "verified_core_data": {
            "brand": "Natufarma",
            "ean": "7795379101108",
            "source_name": "Fabricante",
        },
    }


def test_image_review_approves_authorized_exact_manufacturer_source():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = PrepublicationImageService(db)
        service.prepublication.report = lambda: {
            "mercadolibre_connected": False,
            "items": [prepublication_item()],
        }

        saved = service.save(
            product_key="ECOMM:20",
            status="APPROVED",
            source_type="MANUFACTURER",
            source_name="Natufarma",
            source_url="https://example.com/valeriana",
            image_urls=["https://example.com/valeriana.jpg"],
            match_basis="GTIN_EXACT",
            exact_match=True,
            authorized_for_use=True,
            notes="Presentación exacta x40.",
        )

        assert saved["image_status"] == "APPROVED"
        assert saved["source_type"] == "MANUFACTURER"
        assert saved["image_urls"] == ["https://example.com/valeriana.jpg"]


def test_other_seller_can_be_reference_but_cannot_be_approved():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = PrepublicationImageService(db)
        service.prepublication.report = lambda: {
            "mercadolibre_connected": False,
            "items": [prepublication_item()],
        }

        draft = service.save(
            product_key="ECOMM:20",
            status="DRAFT",
            source_type="OTHER_SELLER",
            source_name="Publicación de referencia",
            source_url="https://example.com/listing",
            image_urls=["https://example.com/photo.jpg"],
            match_basis="MANUAL_EXACT",
            exact_match=True,
        )
        assert draft["image_status"] == "DRAFT"

        with pytest.raises(ValueError, match="otro vendedor"):
            service.save(
                product_key="ECOMM:20",
                status="APPROVED",
                source_type="OTHER_SELLER",
                source_name="Publicación de referencia",
                source_url="https://example.com/listing",
                image_urls=["https://example.com/photo.jpg"],
                match_basis="MANUAL_EXACT",
                exact_match=True,
                authorized_for_use=True,
            )


def test_prepublication_marks_images_passed_only_after_approval():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(
            PrepublicationImageReview(
                product_key="ECOMM:20",
                status="APPROVED",
                source_type="MANUFACTURER",
                source_name="Natufarma",
                source_url="https://example.com/valeriana",
                image_urls=["https://example.com/valeriana.jpg"],
                match_basis="GTIN_EXACT",
                exact_match=True,
                authorized_for_use=True,
                product_snapshot={},
                history=[],
            )
        )
        db.commit()

        service = PrepublicationService(db)
        service.readiness.report = lambda: {
            "items": [
                {
                    "product": {
                        "ecomm_id": "20",
                        "sku": "A20",
                        "name": "Valeriana Natufarma x 40",
                        "stock": 12,
                        "price": 1000,
                        "brand": "Natufarma",
                        "ean": "7795379101108",
                    },
                    "readiness_status": "READY_CORE_DATA",
                    "reason_codes": [],
                }
            ]
        }

        report = service.report()
        assert report["summary"]["approved_images"] == 1
        assert report["summary"]["waiting_images"] == 0
        assert report["items"][0]["checks"]["images"] == "PASSED"
