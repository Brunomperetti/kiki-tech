import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import (
    Base,
    PrepublicationImageReview,
    PrepublicationMetadataReview,
)
from app.services.final_publication_queue_service import FinalPublicationQueueService


def base_item():
    return {
        "product_key": "ECOMM:20",
        "product": {
            "ecomm_id": "20",
            "sku": "1286",
            "name": "Valeriana Natufarma x 40",
            "stock": 12,
            "price": 8000,
            "brand": "Natufarma",
            "ean": "7795379101108",
        },
        "verified_core_data": {
            "brand": "Natufarma",
            "ean": "7795379101108",
        },
        "checks": {
            "core_data": "PASSED",
            "images": "PASSED",
            "category": "PASSED",
            "attributes": "PASSED",
            "preview": "READY_TO_VALIDATE",
        },
    }


def seed_external_controls(db):
    db.add(
        PrepublicationImageReview(
            product_key="ECOMM:20",
            status="APPROVED",
            source_type="MANUFACTURER",
            source_name="Natufarma",
            source_url="https://example.com/product",
            image_urls=["https://example.com/product.jpg"],
            match_basis="GTIN_EXACT",
            exact_match=True,
            authorized_for_use=True,
            product_snapshot={},
            history=[],
        )
    )
    db.add(
        PrepublicationMetadataReview(
            product_key="ECOMM:20",
            status="APPROVED",
            category_id="MLA123",
            category_name="Suplementos dietarios",
            domain_id="MLA-SUPPLEMENTS",
            domain_name="Suplementos",
            candidates=[],
            attributes=[
                {
                    "id": "BRAND",
                    "name": "Marca",
                    "verified_value": "Natufarma",
                    "required": True,
                },
                {
                    "id": "GTIN",
                    "name": "GTIN",
                    "verified_value": "7795379101108",
                    "required": True,
                },
            ],
            required_missing=[],
            product_snapshot={},
            history=[],
        )
    )
    db.commit()


def test_final_queue_requires_explicit_human_approval():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_external_controls(db)
        service = FinalPublicationQueueService(db)
        service.prepublication.report = lambda: {"items": [base_item()]}

        queue = service.queue()

        assert queue["summary"]["READY_FOR_FINAL_REVIEW"] == 1
        assert queue["summary"]["APPROVED_FOR_PUBLICATION"] == 0
        item = queue["items"][0]
        assert item["queue_status"] == "READY_FOR_FINAL_REVIEW"
        assert item["blockers"] == []
        assert item["preview"]["category_id"] == "MLA123"
        assert item["preview"]["image_urls"] == ["https://example.com/product.jpg"]


def test_final_approval_persists_and_enters_publication_batch_queue():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_external_controls(db)
        service = FinalPublicationQueueService(db)
        service.prepublication.report = lambda: {"items": [base_item()]}

        saved = service.save_approval(
            "ECOMM:20",
            "APPROVE",
            "Revisado y aprobado para lote.",
        )

        assert saved["queue_status"] == "APPROVED_FOR_PUBLICATION"
        assert saved["approved_at"]
        refreshed = service.queue()
        assert refreshed["summary"]["APPROVED_FOR_PUBLICATION"] == 1


def test_final_approval_becomes_stale_if_images_change():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_external_controls(db)
        service = FinalPublicationQueueService(db)
        service.prepublication.report = lambda: {"items": [base_item()]}
        service.save_approval("ECOMM:20", "APPROVE")

        image = db.query(PrepublicationImageReview).filter_by(product_key="ECOMM:20").one()
        image.image_urls = ["https://example.com/new-product.jpg"]
        db.commit()

        item = service.queue()["items"][0]

        assert item["queue_status"] == "STALE_APPROVAL"


def test_blocked_product_cannot_be_approved():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed_external_controls(db)
        blocked = base_item()
        blocked["checks"] = dict(blocked["checks"])
        blocked["checks"]["images"] = "WAITING_IMAGE_DATA"

        service = FinalPublicationQueueService(db)
        service.prepublication.report = lambda: {"items": [blocked]}

        queue_item = service.queue()["items"][0]
        assert queue_item["queue_status"] == "BLOCKED"
        assert "Imágenes" in queue_item["blockers"]

        with pytest.raises(ValueError, match="todavía no pasó todos"):
            service.save_approval("ECOMM:20", "APPROVE")
