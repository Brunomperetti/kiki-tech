import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base, InventoryLinkageDecision, ReconciliationRun
from app.services.inventory_linkage_service import InventoryLinkageService


def product(ecomm_id, sku, ean, name, ecomm_rows=None):
    return {
        "ecomm_id": ecomm_id,
        "sku": sku,
        "sku_effective": sku,
        "ean": ean,
        "ean_aliases": [ean],
        "name": name,
        "brand": "Marca",
        "stock": 5,
        "ecomm_rows": ecomm_rows or [],
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
        assert ready["match_method"] == "GTIN_EXACT"
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


def test_inventory_linkage_uses_exact_mla_when_ecomm_gtin_is_missing():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [
                product(
                    "10",
                    "1175",
                    None,
                    "Aceite MCT",
                    ecomm_rows=[
                        {
                            "listing_id": "MLA1889257682",
                            "marketplace_id": None,
                        }
                    ],
                )
            ],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                edima(
                    "MLA1889257682",
                    "No",
                    "7798318384006",
                    ["7798318384006"],
                    "Aceite MCT ML",
                )
            ],
        )

        item = service.report()["items"][0]

        assert item["status"] == "READY_TO_LINK"
        assert item["match_method"] == "ECOMM_MLA"
        assert item["matched_product"]["sku"] == "1175"
        assert "MLA1889257682" in item["reason"]


def test_inventory_linkage_blocks_when_mla_and_existing_gtin_conflict():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [
                product(
                    "10",
                    "1175",
                    "7798121272958",
                    "Producto Ecomm",
                    ecomm_rows=[{"listing_id": "MLA1889257682"}],
                )
            ],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                edima(
                    "MLA1889257682",
                    "No",
                    "7798318384006",
                    ["7798318384006"],
                )
            ],
        )

        item = service.report()["items"][0]

        assert item["status"] == "REVIEW_IDENTIFIER_CONFLICT"
        assert item["match_method"] == "ECOMM_MLA_GTIN_CONFLICT"
        assert item["matched_product"]["sku"] == "1175"


def test_inventory_linkage_accepts_numeric_marketplace_id_for_mla():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [
                product(
                    "10",
                    "1175",
                    None,
                    "Aceite MCT",
                    ecomm_rows=[{"marketplace_id": "1889257682"}],
                )
            ],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                edima(
                    "MLA1889257682",
                    "No",
                    "7798318384006",
                    ["7798318384006"],
                )
            ],
        )

        item = service.report()["items"][0]

        assert item["status"] == "READY_TO_LINK"
        assert item["match_method"] == "ECOMM_MLA"


def test_inventory_linkage_blocks_ambiguous_gtin_even_when_mla_matches_one_product():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [
                product(
                    "10",
                    "1000",
                    "7798121272958",
                    "Producto A",
                    ecomm_rows=[{"listing_id": "MLA1889257682"}],
                ),
                product("20", "2000", "7798121272958", "Producto B"),
            ],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                edima(
                    "MLA1889257682",
                    "No",
                    "7798121272958",
                    ["7798121272958"],
                )
            ],
        )

        item = service.report()["items"][0]

        assert item["status"] == "REVIEW_AMBIGUOUS"
        assert item["match_method"] == "ECOMM_MLA_GTIN_AMBIGUOUS"


def test_inventory_linkage_uses_latest_reconciliation_mla_when_raw_ecomm_has_no_listing_id():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        canonical = product("10", "1175", None, "Aceite MCT")
        service.repo.save_snapshot("ECOMM_APP", [canonical])
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                edima(
                    "MLA1889257682",
                    "No",
                    "7798318384006",
                    ["7798318384006"],
                    "Aceite MCT ML",
                )
            ],
        )
        service.repo.add_run(
            ReconciliationRun(
                results=[
                    {
                        "product": canonical,
                        "listing": {
                            "external_id": "MLA1889257682",
                            "title": "Aceite MCT ML",
                        },
                        "matched_listing_ids": ["MLA1889257682"],
                        "status": "ALREADY_PUBLISHED",
                    }
                ],
                summary={"total_products": 1, "total_listings": 1},
            )
        )

        item = service.report()["items"][0]

        assert item["status"] == "READY_TO_LINK"
        assert item["match_method"] == "RECONCILIATION_MLA"
        assert item["decision_source"] == "AUTOMATIC_IDENTIFIERS"
        assert item["decision_at"] is None
        assert item["matched_product"]["sku"] == "1175"


def test_reconciliation_mla_takes_priority_over_gtin_fallback():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        published = product("10", "1175", None, "Aceite MCT")
        another = product("20", "2000", "7798318384006", "Otro producto")
        service.repo.save_snapshot("ECOMM_APP", [published, another])
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                edima(
                    "MLA1889257682",
                    "No",
                    "7798318384006",
                    ["7798318384006"],
                )
            ],
        )
        service.repo.add_run(
            ReconciliationRun(
                results=[
                    {
                        "product": published,
                        "listing": {"external_id": "MLA1889257682"},
                        "matched_listing_ids": ["MLA1889257682"],
                        "status": "ALREADY_PUBLISHED",
                    }
                ],
                summary={"total_products": 2, "total_listings": 1},
            )
        )

        item = service.report()["items"][0]

        assert item["status"] == "REVIEW_IDENTIFIER_CONFLICT"
        assert item["match_method"] == "RECONCILIATION_MLA_GTIN_CONFLICT"


def test_inventory_linkage_suggests_unique_exact_title_when_identifiers_fail():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [
                product(
                    "10",
                    "1175",
                    None,
                    "Aceite De Girasol Orgánico Dicomere 500 Ml",
                )
            ],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                edima(
                    "MLA3235792624",
                    "No",
                    "7793323024763",
                    ["7793323024763"],
                    "Aceite De Girasol Orgánico Dicomere 500 Ml",
                )
            ],
        )

        item = service.report()["items"][0]

        assert item["status"] == "REVIEW_TITLE_CANDIDATE"
        assert item["match_method"] == "TITLE_EXACT"
        assert item["matched_product"]["sku"] == "1175"
        assert service.report()["summary"]["title_candidates"] == 1


def test_inventory_linkage_suggests_only_clear_high_confidence_title():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [
                product(
                    "10",
                    "1175",
                    None,
                    "Aceite De Girasol Organico Dicomere 500ml",
                ),
                product(
                    "20",
                    "2000",
                    None,
                    "Aceite De Coco Organico 500ml",
                ),
            ],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                edima(
                    "MLA3235792624",
                    "No",
                    "7793323024763",
                    ["7793323024763"],
                    "Aceite De Girasol Organico Dicomere 500 Ml",
                )
            ],
        )

        item = service.report()["items"][0]

        assert item["status"] == "REVIEW_TITLE_CANDIDATE"
        assert item["match_method"] in {"TITLE_EXACT", "TITLE_HIGH_CONFIDENCE"}
        assert item["matched_product"]["sku"] == "1175"


def test_inventory_linkage_does_not_use_ambiguous_title():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [
                product("10", "1000", None, "Producto Natural 500 Ml"),
                product("20", "2000", None, "Producto Natural 500 Ml"),
            ],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                edima(
                    "MLA999",
                    "No",
                    "7793323024763",
                    ["7793323024763"],
                    "Producto Natural 500 Ml",
                )
            ],
        )

        item = service.report()["items"][0]

        assert item["status"] == "NO_ECOMM_MATCH"
        assert item["matched_product"] is None


def test_human_confirmation_promotes_title_candidate_to_ready():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [product("10", "1175", None, "Aceite De Girasol Orgánico Dicomere 500 Ml")],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                edima(
                    "MLA3235792624",
                    "No",
                    "7793323024763",
                    ["7793323024763"],
                    "Aceite De Girasol Orgánico Dicomere 500 Ml",
                )
            ],
        )

        before = service.report()["items"][0]
        assert before["status"] == "REVIEW_TITLE_CANDIDATE"

        saved = service.save_decision(
            "MLA3235792624",
            "CONFIRMED",
            "10",
        )

        assert saved["status"] == "READY_TO_LINK"
        assert saved["match_method"] == "HUMAN_CONFIRMED_TITLE"
        assert saved["decision_status"] == "CONFIRMED"
        assert saved["decision_source"] == "HUMAN_KIKI"
        assert saved["decision_at"]
        report = service.report()
        assert report["summary"]["ready_to_link"] == 1
        assert report["summary"]["confirmed_by_human"] == 1
        assert report["summary"]["review_required"] == 0


def test_human_rejection_keeps_title_candidate_in_review():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [product("10", "1175", None, "Aceite De Girasol Orgánico Dicomere 500 Ml")],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                edima(
                    "MLA3235792624",
                    "No",
                    "7793323024763",
                    ["7793323024763"],
                    "Aceite De Girasol Orgánico Dicomere 500 Ml",
                )
            ],
        )

        saved = service.save_decision(
            "MLA3235792624",
            "REJECTED",
            "10",
        )

        assert saved["status"] == "REVIEW_TITLE_CANDIDATE"
        assert saved["decision_status"] == "REJECTED"
        report = service.report()
        assert report["summary"]["ready_to_link"] == 0
        assert report["summary"]["review_required"] == 1


def test_human_confirmation_becomes_stale_if_edima_evidence_changes():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [product("10", "1175", None, "Aceite De Girasol Orgánico Dicomere 500 Ml")],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                edima(
                    "MLA3235792624",
                    "No",
                    "7793323024763",
                    ["7793323024763"],
                    "Aceite De Girasol Orgánico Dicomere 500 Ml",
                )
            ],
        )
        service.save_decision("MLA3235792624", "CONFIRMED", "10")

        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                edima(
                    "MLA3235792624",
                    "No",
                    "7798318384006",
                    ["7798318384006"],
                    "Aceite De Girasol Orgánico Dicomere 500 Ml",
                )
            ],
        )
        item = service.report()["items"][0]

        assert item["status"] == "REVIEW_TITLE_CANDIDATE"
        assert item["decision_status"] == "STALE"
        assert service.report()["summary"]["ready_to_link"] == 0


def test_human_confirmation_rejects_changed_product_identifier():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [product("10", "1175", None, "Aceite De Girasol Orgánico Dicomere 500 Ml")],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                edima(
                    "MLA3235792624",
                    "No",
                    "7793323024763",
                    ["7793323024763"],
                    "Aceite De Girasol Orgánico Dicomere 500 Ml",
                )
            ],
        )

        with pytest.raises(ValueError, match="producto Ecomm sugerido cambió"):
            service.save_decision(
                "MLA3235792624",
                "CONFIRMED",
                "999",
            )


def test_offline_evidence_surfaces_candidate_when_normal_matching_fails():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [product("6708437", "246", None, "Pasta De Mani Natural Mani King X 485g Sin Tacc")],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                edima(
                    "MLA1903337428",
                    "No",
                    "7798151952332",
                    ["7798151952332"],
                    "Publicación con título diferente",
                )
            ],
        )
        service.repo.save_snapshot(
            "OFFLINE_LINKAGE_EVIDENCE",
            [
                {
                    "external_id": "MLA1903337428",
                    "gtin": "7798151952332",
                    "candidate_ecomm_id": "6708437",
                    "candidate_product": "Pasta De Mani Natural Mani King X 485g Sin Tacc",
                    "evidence_type": "SKU_EXACT_HISTORICAL",
                    "recommendation": "CONFIRMAR CANDIDATO",
                    "note": "Coincidencia histórica por SKU exacto.",
                }
            ],
        )

        item = service.report()["items"][0]

        assert item["status"] == "REVIEW_OFFLINE_CANDIDATE"
        assert item["matched_product"]["ecomm_id"] == "6708437"
        assert item["match_method"] == "OFFLINE_SKU_EXACT_HISTORICAL"
        assert item["offline_evidence"]["recommendation"] == "CONFIRMAR CANDIDATO"
        assert service.report()["summary"]["offline_candidates"] == 1


def test_human_confirmation_promotes_offline_candidate_to_ready():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [product("6708437", "246", None, "Pasta De Mani Natural Mani King X 485g Sin Tacc")],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                edima(
                    "MLA1903337428",
                    "No",
                    "7798151952332",
                    ["7798151952332"],
                    "Publicación con título diferente",
                )
            ],
        )
        service.repo.save_snapshot(
            "OFFLINE_LINKAGE_EVIDENCE",
            [
                {
                    "external_id": "MLA1903337428",
                    "gtin": "7798151952332",
                    "candidate_ecomm_id": "6708437",
                    "evidence_type": "SKU_EXACT_HISTORICAL",
                    "recommendation": "CONFIRMAR CANDIDATO",
                    "note": "Coincidencia histórica por SKU exacto.",
                }
            ],
        )

        saved = service.save_decision(
            "MLA1903337428",
            "CONFIRMED",
            "6708437",
        )

        assert saved["status"] == "READY_TO_LINK"
        assert saved["match_method"] == "HUMAN_CONFIRMED_OFFLINE"
        assert saved["decision_status"] == "CONFIRMED"
        assert service.report()["summary"]["confirmed_by_human"] == 1


def test_save_decision_does_not_recompute_full_report():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [product("6708437", "246", None, "Pasta De Mani Natural Mani King X 485g Sin Tacc")],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                edima(
                    "MLA1903337428",
                    "No",
                    "7798151952332",
                    ["7798151952332"],
                    "Publicación con título diferente",
                )
            ],
        )
        service.repo.save_snapshot(
            "OFFLINE_LINKAGE_EVIDENCE",
            [
                {
                    "external_id": "MLA1903337428",
                    "gtin": "7798151952332",
                    "candidate_ecomm_id": "6708437",
                    "evidence_type": "SKU_EXACT_HISTORICAL",
                    "recommendation": "CONFIRMAR CANDIDATO",
                    "note": "Coincidencia histórica por SKU exacto.",
                }
            ],
        )

        service.report = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("save_decision no debe recalcular el reporte completo")
        )

        saved = service.save_decision(
            "MLA1903337428",
            "CONFIRMED",
            "6708437",
        )

        assert saved["status"] == "READY_TO_LINK"
        assert saved["decision_status"] == "CONFIRMED"
        assert saved["match_method"] == "HUMAN_CONFIRMED_OFFLINE"


def test_manual_candidate_search_suggests_similar_ecomm_products():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [
                product("10", "3370", None, "Potasio Natier X 50 Caps"),
                product("20", "5154", None, "Vitamina K2 Natier 50 Caps"),
            ],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                edima(
                    "MLA100",
                    "No",
                    "7798121272958",
                    ["7798121272958"],
                    "Capsulas De Potasio Natier X 50",
                )
            ],
        )

        result = service.search_candidates("MLA100")

        assert result["external_id"] == "MLA100"
        assert result["candidates"]
        assert result["candidates"][0]["ecomm_id"] == "10"
        assert result["candidates"][0]["score"] > 0.5


def test_manual_candidate_search_supports_exact_sku():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [
                product("10", "3370", None, "Potasio Natier X 50 Caps"),
                product("20", "5154", None, "Vitamina K2 Natier 50 Caps"),
            ],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [edima("MLA100", "No", "7799999999994", ["7799999999994"])],
        )

        result = service.search_candidates("MLA100", search="5154")

        assert len(result["candidates"]) == 1
        assert result["candidates"][0]["ecomm_id"] == "20"
        assert result["candidates"][0]["score"] == 1.0
        assert "Identificador exacto" in result["candidates"][0]["reasons"]


def test_manual_assignment_promotes_unmatched_row_and_persists_decision():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [product("10", "3370", None, "Potasio Natier X 50 Caps")],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                edima(
                    "MLA100",
                    "No",
                    "7798121272958",
                    ["7798121272958"],
                    "Publicacion sin coincidencia automatica",
                )
            ],
        )

        before = service.report()["items"][0]
        assert before["status"] == "NO_ECOMM_MATCH"

        saved = service.save_manual_assignment("MLA100", "10", "Revisado manualmente")

        assert saved["status"] == "READY_TO_LINK"
        assert saved["match_method"] == "HUMAN_CONFIRMED_MANUAL"
        assert saved["decision_source"] == "HUMAN_KIKI"
        assert saved["matched_product"]["sku"] == "3370"

        refreshed = service.report()["items"][0]
        assert refreshed["status"] == "READY_TO_LINK"
        assert refreshed["match_method"] == "HUMAN_CONFIRMED_MANUAL"
        assert refreshed["decision_status"] == "CONFIRMED"
        assert refreshed["matched_product"]["ecomm_id"] == "10"


def test_manual_assignment_does_not_override_identifier_conflict():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [
                product(
                    "10",
                    "1000",
                    "7798121272958",
                    "Producto A",
                    ecomm_rows=[{"listing_id": "MLA100"}],
                ),
                product("20", "2000", "7798318384006", "Producto B"),
            ],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [edima("MLA100", "No", "7798318384006", ["7798318384006"])],
        )

        assert service.report()["items"][0]["status"] == "REVIEW_IDENTIFIER_CONFLICT"

        with pytest.raises(ValueError, match="conflicto de identificadores"):
            service.save_manual_assignment("MLA100", "20")


def test_candidate_search_does_not_suggest_wrong_brand_or_size_automatically():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [
                {
                    **product("10", "1000", None, "Aceite De Girasol Orgánico Pampagourmet X 5L"),
                    "brand": "Pampa Gourmet",
                },
                {
                    **product("20", "2000", None, "Aceite De Oliva Organico Zuelo 500 ml"),
                    "brand": None,
                },
            ],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                {
                    **edima(
                        "MLA100",
                        "No",
                        "7793323024763",
                        ["7793323024763"],
                        "Aceite De Girasol Orgánico Dicomere 500 Ml",
                    ),
                    "brand": "Dicomere",
                }
            ],
        )

        result = service.search_candidates("MLA100")

        assert result["candidates"] == []


def test_candidate_search_marks_explicit_mismatched_size_as_warning():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [
                {
                    **product("10", "1000", None, "Aceite De Girasol Orgánico Dicomere X 5L"),
                    "brand": "Dicomere",
                }
            ],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                {
                    **edima(
                        "MLA100",
                        "No",
                        "7793323024763",
                        ["7793323024763"],
                        "Aceite De Girasol Orgánico Dicomere 500 Ml",
                    ),
                    "brand": "Dicomere",
                }
            ],
        )

        result = service.search_candidates("MLA100", search="1000")

        assert len(result["candidates"]) == 1
        assert "⚠ Presentación distinta" in result["candidates"][0]["reasons"]
        assert result["candidates"][0]["score"] <= 0.45


def test_confirmed_pack_x2_is_reopened_if_candidate_is_unit_product():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [
                {
                    **product("10", "3370", None, "Potasio Natier X 50 Caps"),
                    "brand": "Natier",
                }
            ],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                {
                    **edima(
                        "MLA100",
                        "No",
                        "7798121272958",
                        ["7798121272958"],
                        "Potasio En Capsulas X 50 Sabor Neutro Natier Pack X2",
                    ),
                    "brand": "Natier",
                }
            ],
        )
        service.repo.save_snapshot(
            "OFFLINE_LINKAGE_EVIDENCE",
            [
                {
                    "external_id": "MLA100",
                    "gtin": "7798121272958",
                    "candidate_ecomm_id": "10",
                    "candidate_product": "Potasio Natier X 50 Caps",
                    "evidence_type": "TITLE_INVENTORY_HISTORICAL",
                }
            ],
        )

        db.add(
            InventoryLinkageDecision(
                external_id="MLA100",
                decision="CONFIRMED",
                ecomm_id="10",
                source_snapshot={
                    "title": "Potasio En Capsulas X 50 Sabor Neutro Natier Pack X2",
                    "gtin_raw": "7798121272958",
                    "matched_ecomm_id": "10",
                    "match_method": "OFFLINE_TITLE_INVENTORY_HISTORICAL",
                },
                product_snapshot={"ecomm_id": "10", "sku": "3370", "name": "Potasio Natier X 50 Caps"},
                history=[],
            )
        )
        db.commit()
        item = service.report()["items"][0]

        assert item["status"] == "REVIEW_PRESENTATION_CONFLICT"
        assert item["decision_status"] == "STALE"
        assert "PACK X2" in item["reason"]


def test_manual_assignment_blocks_mismatched_volume():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [
                {
                    **product("10", "1000", None, "Aceite De Girasol Dicomere 5 L"),
                    "brand": "Dicomere",
                }
            ],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                {
                    **edima(
                        "MLA100",
                        "No",
                        "7793323024763",
                        ["7793323024763"],
                        "Aceite De Girasol Dicomere 500 Ml",
                    ),
                    "brand": "Dicomere",
                }
            ],
        )

        with pytest.raises(ValueError, match="presentación no coincide"):
            service.save_manual_assignment("MLA100", "10")


def test_candidate_search_does_not_suggest_different_flavor_variant():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [
                {
                    **product(
                        "10",
                        "4559200",
                        None,
                        "Pack X 2 Café Instantáneo Liofilizado Juan Valdez Avellana",
                    ),
                    "brand": "Juan Valdez",
                }
            ],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                {
                    **edima(
                        "MLA1447707817",
                        "No",
                        "770721631452",
                        ["770721631452"],
                        "Pack X 2 Café Liofilizado Clásico Juan Valdez 50gr",
                    ),
                    "brand": "Juan Valdez",
                }
            ],
        )

        result = service.search_candidates("MLA1447707817")

        assert result["candidates"] == []


def test_manual_assignment_blocks_different_flavor_variant():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = InventoryLinkageService(db)
        service.repo.save_snapshot(
            "ECOMM_APP",
            [
                {
                    **product(
                        "10",
                        "4559200",
                        None,
                        "Pack X 2 Café Instantáneo Liofilizado Juan Valdez Avellana",
                    ),
                    "brand": "Juan Valdez",
                }
            ],
        )
        service.repo.save_snapshot(
            "EDIMA_LINKAGE",
            [
                {
                    **edima(
                        "MLA1447707817",
                        "No",
                        "770721631452",
                        ["770721631452"],
                        "Pack X 2 Café Liofilizado Clásico Juan Valdez 50gr",
                    ),
                    "brand": "Juan Valdez",
                }
            ],
        )

        with pytest.raises(ValueError, match="variante/sabor no coincide"):
            service.save_manual_assignment("MLA1447707817", "10")
