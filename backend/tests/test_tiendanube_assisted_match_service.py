from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base
from app.services.tiendanube_assisted_match_service import (
    TiendanubeAssistedMatchService, pack_units, variant_conflict,
)


def test_assisted_match_suggests_similar_without_writing_or_guessing_gtin():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubeAssistedMatchService(db)
        svc.catalog.repo.save_snapshot("ECOMM_APP", [
            {"ecomm_id": "17", "sku": "LOCAL-17", "name": "Avena tradicional Granix 400 gr", "brand": "Granix"},
            {"ecomm_id": "18", "sku": "LOCAL-18", "name": "Avena tradicional Granix 800 gr", "brand": "Granix"},
        ])
        svc.catalog.repo.save_snapshot("TIENDANUBE", [
            {"slug": "avena", "sku": "TN-1", "name": "Avena tradicional Granix 400 gr",
             "brand": "Granix", "ean_raw": "7798010000000.0"},
        ])
        report = svc.report()
        assert report["summary"]["with_proposals"] == 1
        matches = report["items"][0]["candidates"]
        assert len(matches) == 1
        assert matches[0]["ecomm_id"] == "17"
        assert matches[0]["confidence"] == "HIGH"
        assert svc.catalog.repo.snapshot("TIENDANUBE")[0]["ean_raw"] == "7798010000000.0"
        assert "ean" not in matches[0]


def test_assisted_match_rejects_brand_and_pack_conflicts():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubeAssistedMatchService(db)
        svc.catalog.repo.save_snapshot("ECOMM_APP", [
            {"ecomm_id": "1", "sku": "A", "name": "Crema facial Rosa 250 ml", "brand": "Otra"},
            {"ecomm_id": "2", "sku": "B", "name": "Crema facial Rosa 500 ml", "brand": "Rosa"},
        ])
        svc.catalog.repo.save_snapshot("TIENDANUBE", [
            {"slug": "crema", "sku": "X", "name": "Crema facial Rosa 250 ml", "brand": "Rosa"}
        ])
        report = svc.report()
        assert report["summary"]["with_proposals"] == 0
        assert report["items"][0]["status"] == "NO_SAFE_CANDIDATE"


def test_unit_quantities_reject_different_capsules_and_compact_weights():
    assert pack_units("Pack X 3 Colageno 240 Cápsulas") == {(240, "capsulas")}
    assert pack_units("Pack x3 Colageno 180 caps") == {(180, "capsulas")}
    assert pack_units("Pasta de mani x485g") == {(485, "g")}
    assert pack_units("Pasta de mani X 480 grs") == {(480, "g")}
    assert pack_units("Colageno 30 comprimidos") == {(30, "comprimidos")}
    assert pack_units("Colageno 30 comp") == set()
    assert variant_conflict("Pack X 3 Colageno 240 Cápsulas", "5243200",
                            "Pack X 3 Colageno 180 Cápsulas Neutro", "5243200")
    assert variant_conflict("Pasta de mani 485g", "246", "Pasta de mani 480g", "246")
    assert not variant_conflict("Pasta de mani 485g", "246", "Pasta de mani X 485 gr", "246")
    assert not variant_conflict("Colageno 240 Cápsulas", "5243200",
                                "Colageno", "5243200")  # Unknown remains unconfirmed.
