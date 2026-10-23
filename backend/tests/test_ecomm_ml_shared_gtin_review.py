"""Read-only shared-GTIN evidence when uniquely identifying SKUs exist."""
from copy import deepcopy

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import Base, CatalogSnapshot
from app.integrations.ecomm_app.catalog_stage import STAGE_SOURCE
from app.integrations.ecomm_app.ml_brand_evidence import (
    EcommMlBrandEvidenceService,
    ml_brand_evidence_report,
)
from app.integrations.ecomm_app.ml_shared_gtin_review import shared_gtin_sku_review


EAN = "4006381333931"


def samples():
    groups = [
        (1, "A1", None, EAN),
        (2, "B2", "Brand existing", EAN),
        (3, "C3", None, None),
    ]
    pages = [{
        "page": 1, "total": len(groups), "per_page": 50,
        "total_pages": 1, "captured_at": "2026-10-23T14:00:00+00:00",
        "items": [
            {"code": sku + "_m", "variants": [
                {"id": ident, "sku": sku, "is_combo": ident == 1,
                 "total_stock": 1, "warehouses": [{"id": 2210, "stock": 1}]}
            ]}
            for ident, sku, _, _ in groups
        ],
    }]
    legacy = [
        {"ecomm_id": str(ident), "sku": sku, "sku_effective": sku,
         "sku_variant": sku, "sku_aliases": [sku], "ean": ean,
         "name": f"Producto ejemplo {ident} 100g", "brand": brand}
        for ident, sku, brand, ean in groups
    ]
    ml = [
        {"external_id": "MLA101#123", "sku": "A1", "sku_effective": "A1",
         "variant_sku": "A1", "ean": EAN, "title": "Producto ejemplo 1 100g"},
        {"external_id": "MLA102", "sku": "B2", "ean": EAN,
         "title": "Producto ejemplo 2 100g"},
        {"external_id": "MLA103", "sku": "C3", "ean": EAN,
         "title": "Producto ejemplo 3 100g"},
        {"external_id": "MLA104", "sku": "NO-MATCH", "ean": EAN,
         "title": "Otro producto 100g"},
    ]
    edima = [
        {"external_id": "MLA101", "brand": "Brand A", "gtins": [], "title": "Producto ejemplo 1 100g"},
        {"external_id": "MLA102", "brand": "Brand B", "gtins": [], "title": "Producto ejemplo 2 100g"},
        {"external_id": "MLA103", "brand": "Brand C", "gtins": [], "title": "Producto ejemplo 3 100g"},
        {"external_id": "MLA104", "brand": "Brand D", "gtins": [], "title": "Otro producto 100g"},
    ]
    return pages, legacy, ml, edima


def test_shared_gtin_unique_variant_sku_is_only_review_evidence():
    pages, legacy, ml, edima = samples()
    before = deepcopy((pages, legacy, ml, edima))
    report = ml_brand_evidence_report(pages, legacy, ml, edima, "MERCADOLIBRE_API")
    assert report["activation_allowed"] is False
    assert report["summary"]["unique_brand_review_leads"] == 0
    diag = report["shared_gtin_review"]
    counts = diag["counts"]
    assert counts["shared_gtin_ml_rows"] == 4
    assert counts["unique_sku_despite_shared_gtin"] == 3
    assert counts["explicit_unique_variant_sku"] == 1
    assert counts["already_branded_ecomm"] == 1
    assert counts["identity_contradiction"] == 1
    assert counts["no_unique_exact_sku"] == 1
    assert counts["sku_consistent_missing_brand_rows"] == 1
    assert counts["possible_ecomm_brand_review_ids"] == 1
    assert len(diag["review_leads"]) == 1
    lead = diag["review_leads"][0]
    assert lead["ecomm_id"] == "1"
    assert lead["mla"] == "MLA101"
    assert lead["ml_brand"] == "Brand A"
    assert lead["brand_source"] == "EDIMA_LINKAGE"
    assert lead["exact_variant_sku"] is True
    assert lead["shared_gtin_ecomm_owner_count"] == 2
    assert lead["review_status"] == "NEEDS_HUMAN_VERIFICATION"
    assert (pages, legacy, ml, edima) == before


def test_variation_specific_brand_conflict_blocks_multiple_leads():
    pages, legacy, ml, edima = samples()
    ml.append({
        "external_id": "MLA105", "sku": "A1", "ean": EAN,
        "title": "Producto ejemplo 1 100g",
    })
    edima.append({"external_id": "MLA105", "brand": "Different", "gtins": []})
    report = ml_brand_evidence_report(pages, legacy, ml, edima, "MERCADOLIBRE_API")
    diag = report["shared_gtin_review"]
    assert diag["counts"]["conflicting_brands_same_ecomm"] == 1
    assert diag["counts"]["possible_ecomm_brand_review_ids"] == 0
    assert diag["review_leads"] == []


def test_invalid_ean_and_ambiguous_sku_are_not_review_candidates():
    pages, legacy, ml, edima = samples()
    ml[0]["ean"] = "4006381333932"
    ml[1]["sku"] = "WRONG"
    report = ml_brand_evidence_report(pages, legacy, ml, edima, "MERCADOLIBRE_API")
    assert report["shared_gtin_review"]["review_leads"] == []


def test_read_only_service_does_not_change_any_snapshot():
    pages, legacy, ml, edima = samples()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        values = [
            (STAGE_SOURCE, pages),
            ("ECOMM_APP", legacy),
            ("MERCADOLIBRE_API", ml),
            ("EDIMA_LINKAGE", edima),
            ("TIENDANUBE", [{"sku": "TN"}]),
        ]
        for source, payload in values:
            db.add(CatalogSnapshot(source=source, payload=payload))
        db.commit()
        result = EcommMlBrandEvidenceService(db).report()
        assert result["shared_gtin_review"]["counts"]["possible_ecomm_brand_review_ids"] == 1
        for source, payload in values:
            existing = db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == source))
            assert existing.payload == payload
    engine.dispose()


def test_shared_gtin_weak_evidence_never_associates_contradictory_mla():
    pages, legacy, ml, edima = samples()
    owners_sku = {"a1": {"1"}, "b2": {"2"}, "c3": {"3"}}
    owners_ean = {EAN: {"1", "2"}}
    owners_mla = {"MLA101": {"2"}}
    matched = {"1": (legacy[0], pages[0]["items"][0]["variants"][0])}
    report = shared_gtin_sku_review(
        matched, owners_sku, owners_ean, owners_mla, [ml[0]],
        {"MLA101": {"Brand A"}},
    )
    assert report["counts"]["identity_contradiction"] == 1
    assert report["counts"]["possible_ecomm_brand_review_ids"] == 0
    assert len(report["rejected_samples"]) == 1


def test_capsule_presentation_conflict_is_not_a_brand_candidate():
    # The actual KIKI finding: Ecomm pack x3 240 cápsulas vs ML x3 180.
    pages, legacy, ml, edima = samples()
    legacy[0]["name"] = "Pack X 3 Colágeno + Calcio Vitamin Way 240 Cápsulas"
    ml[0]["title"] = "Pack X 3 Colágeno + Calcio Vitamin Way 180 Cápsulas Neutro"
    result = ml_brand_evidence_report(pages, legacy, ml, edima, "MERCADOLIBRE_API")
    report = result["shared_gtin_review"]
    assert report["counts"]["presentation_conflict"] == 1
    assert report["counts"]["possible_ecomm_brand_review_ids"] == 0
    assert report["review_leads"] == []
    row = report["presentation_rejected_samples"][0]
    assert row["ecomm_id"] == "1"
    assert "240 Cápsulas" in row["ecomm_name"]
    assert "180 Cápsulas" in row["ml_title"]
    assert row["review_status"] == "PRESENTATION_CONFLICT"
    assert result["activation_allowed"] is False


def test_same_485g_peanut_product_remains_eligible_only_as_review_hint():
    pages, legacy, ml, edima = samples()
    legacy[0]["name"] = "Pasta De Mani Natural Mani King X 485g Sin Tacc"
    ml[0]["title"] = "Pasta De Mani Natural Mani King X 485g"
    result = ml_brand_evidence_report(pages, legacy, ml, edima, "MERCADOLIBRE_API")
    report = result["shared_gtin_review"]
    assert report["counts"]["possible_ecomm_brand_review_ids"] == 1
    assert report["review_leads"][0]["review_status"] == "NEEDS_HUMAN_VERIFICATION"


def test_precise_conflicting_gtin_reason_excludes_mla_when_none_exists():
    pages, legacy, ml, edima = samples()
    owners_sku = {"a1": {"1"}}
    owners_ean = {EAN: {"2", "3"}}
    report = shared_gtin_sku_review(
        {"1": (legacy[0], pages[0]["items"][0]["variants"][0])},
        owners_sku, owners_ean, {}, [ml[0]],
        {"MLA101": {"Brand A"}},
    )
    counts = report["counts"]
    assert counts["identity_contradiction"] == 1
    assert counts["sku_outside_gtin_owners"] == 1
    assert counts["historical_mla_conflict"] == 0
    case = report["rejected_samples"][0]
    assert case["reason_codes"] == ["SKU_NOT_IN_GTIN_OWNERS"]
    assert case["sku_ecomm_id"] == "1"
    assert case["gtin_owner_ids"] == ["2", "3"]


def test_precise_historical_mla_conflict_with_sku_inside_gtin_group():
    pages, legacy, ml, edima = samples()
    owners_sku = {"a1": {"1"}}
    owners_ean = {EAN: {"1", "2"}}
    report = shared_gtin_sku_review(
        {"1": (legacy[0], pages[0]["items"][0]["variants"][0])},
        owners_sku, owners_ean, {"MLA101": {"2"}}, [ml[0]],
        {"MLA101": {"Brand A"}},
    )
    assert report["counts"]["identity_contradiction"] == 1
    assert report["counts"]["sku_outside_gtin_owners"] == 0
    assert report["counts"]["historical_mla_conflict"] == 1
    assert report["rejected_samples"][0]["reason_codes"] == ["HISTORICAL_MLA_POINTS_ELSEWHERE"]
    assert report["counts"]["possible_ecomm_brand_review_ids"] == 0
