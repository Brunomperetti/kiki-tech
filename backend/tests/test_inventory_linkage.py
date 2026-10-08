from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base
from app.services.inventory_linkage_service import InventoryLinkageService


def product(ecomm_id, sku, ean, name):
    return {
        "ecomm_id": ecomm_id,
        "sku": sku,
        "sku_effective": sku,
        "ean": ean,
        "ean_aliases": [ean],
        "name": name,
        "brand": "Marca",
        "stock": 5,
    }


def edima(mla, linked, gtin_raw, gtins, title="Publicación"):
    return {
        "external_id": mla,
        "variation_id": "43",
        "title": title,
        "brand": "Marca",
        "inventory_linked": linked,
        "modified_at": "2026-10-08 10:00:00",
        "gtin_raw": gtin_raw,
        "gtins": gtins,
    }


def test_inventory_linkage_matches_only_unique_exact_gtin():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [
                product("10", "1175", "7798318384006", "Aceite MCT"),
                product("20", "2000", "7798121272958", "Potasio"),
            ],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                edima("MLA1", "Sí", "7798121272958", ["7798121272958"]),
                edima("MLA2", "No", "7798318384006", ["7798318384006"], "Aceite MCT ML"),
                edima("MLA3", "No", "074312017070", ["074312017070"], "Sin match"),
                edima(
                    "MLA4",
                    "No",
                    "7798318384006,074312017070",
                    ["7798318384006", "074312017070"],
                    "Dos códigos",
                ),
                edima("MLA5", "No", "43", ["43"], "Código inválido"),
            ],
        )

        report = service.report()

        assert report["available"] is True
        assert report["summary"]["total_publications"] == 5
        assert report["summary"]["linked"] == 1
        assert report["summary"]["unlinked"] == 4
        assert report["summary"]["ready_to_link"] == 1
        assert report["summary"]["review_required"] == 3
        ready = next(item for item in report["items"] if item["external_id"] == "MLA2")
        assert ready["status"] == "READY_TO_LINK"
        assert ready["matched_product"]["sku"] == "1175"
        assert next(item for item in report["items"] if item["external_id"] == "MLA3")["status"] == "NO_ECOMM_MATCH"
        assert next(item for item in report["items"] if item["external_id"] == "MLA4")["status"] == "REVIEW_MULTIPLE_GTIN"
        assert next(item for item in report["items"] if item["external_id"] == "MLA5")["status"] == "INVALID_GTIN"


def test_inventory_linkage_blocks_gtin_owned_by_multiple_ecomm_products():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [
                product("10", "1000", "7798121272958", "Producto A"),
                product("20", "2000", "7798121272958", "Producto B"),
            ],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [edima("MLA9", "No", "7798121272958", ["7798121272958"])],
        )

        item = service.report()["items"][0]

        assert item["status"] == "REVIEW_AMBIGUOUS"
        assert item["matched_product"] is None


def test_inventory_linkage_is_optional_until_edima_is_imported():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        report = InventoryLinkageService(db).report()

        assert report["available"] is False
        assert report["items"] == []
