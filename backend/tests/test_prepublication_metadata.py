from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base
from app.services.prepublication_metadata_service import PrepublicationMetadataService


class FakeMercadoLibre:
    def predict_categories(self, title, limit=3):
        assert title == "Valeriana Natufarma x 40"
        assert limit == 3
        return [
            {
                "domain_id": "MLA-SUPPLEMENTS",
                "domain_name": "Suplementos",
                "category_id": "MLA123",
                "category_name": "Suplementos dietarios",
                "attributes": [
                    {"id": "BRAND", "value_name": "Natufarma"},
                    {"id": "MODEL", "value_name": "Valeriana"},
                ],
            },
            {
                "domain_id": "MLA-HEALTH",
                "domain_name": "Salud",
                "category_id": "MLA999",
                "category_name": "Otros",
                "attributes": [],
            },
        ]

    def category_attributes(self, category_id):
        assert category_id in {"MLA123", "MLA999"}
        return [
            {
                "id": "BRAND",
                "name": "Marca",
                "value_type": "string",
                "tags": {"required": True},
            },
            {
                "id": "GTIN",
                "name": "Código universal de producto",
                "value_type": "string",
                "tags": {"required": True},
            },
            {
                "id": "MODEL",
                "name": "Modelo",
                "value_type": "string",
                "tags": {"required": True},
            },
            {
                "id": "COLOR",
                "name": "Color",
                "value_type": "string",
                "tags": {"conditional_required": True},
            },
        ]


def prepublication_report():
    return {
        "mercadolibre_connected": True,
        "items": [
            {
                "product_key": "ECOMM:1",
                "product": {
                    "ecomm_id": "1",
                    "sku": "1286",
                    "name": "Valeriana Natufarma x 40",
                    "brand": "Natufarma",
                    "ean": "7795379101108",
                    "stock": 10,
                },
                "verified_core_data": {
                    "brand": "Natufarma",
                    "ean": "7795379101108",
                },
                "checks": {"images": "PASSED"},
            }
        ],
    }


def test_analyze_metadata_uses_ml_predictor_and_keeps_human_approval():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = PrepublicationMetadataService(db, FakeMercadoLibre())
        service.prepublication.report = prepublication_report

        analyzed = service.analyze("ECOMM:1")

        assert analyzed["metadata_status"] == "READY_FOR_REVIEW"
        assert analyzed["category_id"] == "MLA123"
        assert len(analyzed["candidates"]) == 2
        assert analyzed["required_missing"] == [{"id": "MODEL", "name": "Modelo"}]
        brand = next(a for a in analyzed["attributes"] if a["id"] == "BRAND")
        gtin = next(a for a in analyzed["attributes"] if a["id"] == "GTIN")
        assert brand["verified_value"] == "Natufarma"
        assert gtin["verified_value"] == "7795379101108"

        approved = service.save(
            product_key="ECOMM:1",
            status="APPROVED",
            category_id="MLA123",
            notes="Categoría confirmada manualmente",
        )
        assert approved["metadata_status"] == "APPROVED"
        assert approved["history_count"] == 2
        assert approved["required_missing"][0]["id"] == "MODEL"


def test_queue_does_not_call_ml_until_user_or_batch_analyzes():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = PrepublicationMetadataService(db, FakeMercadoLibre())
        service.prepublication.report = prepublication_report

        queue = service.queue()

        assert queue["summary"]["total"] == 1
        assert queue["summary"]["DRAFT"] == 1
        assert queue["items"][0]["candidates"] == []
