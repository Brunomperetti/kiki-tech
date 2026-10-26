from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base
from app.services.tiendanube_assisted_match_service import (
    TiendanubeAssistedMatchService, variant_conflict,
)
from test_tiendanube_assisted_match_service import save_api_catalog


def test_variants_do_not_confuse_flavors_or_pack_units():
    assert variant_conflict("Vitaneral vitaminas HMB x240 g", "Vitaneral Vainilla",
                            "Vitaneral vitaminas HMB x240 g", "VITANERALCHOCOLATE")
    assert not variant_conflict("Vitaneral vitaminas HMB x240 g", "Vitaneral Vainilla",
                                "Vitaneral vitaminas HMB x240 g", "VITANERALVAINILLA")
    assert variant_conflict("Jabon x100 g", "A", "Jabon x100 ml", "B")
    assert variant_conflict("Crema 100 g", "A", "Crema 200 g", "B")
    assert not variant_conflict("Jabon x100 gr", "A", "Jabon x100 g", "B")


def test_only_vainilla_is_offered_as_match():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubeAssistedMatchService(db)
        tn = [{"slug": "vitaneral", "sku": "Vitaneral Vainilla",
               "name": "Vitaneral Natufarma Vitaminas y Minerales HMB x240 g",
               "brand": "Natufarma"}]
        ec = [
            {"ecomm_id": "vainilla", "sku": "VITANERALVAINILLA",
             "name": "Vitaneral Natufarma Vitaminas y Minerales + HMB x240gs",
             "brand": "Natufarma"},
            {"ecomm_id": "chocolate", "sku": "VITANERALCHOCOLATE",
             "name": "Vitaneral Natufarma Vitaminas y Minerales + HMB x240gs",
             "brand": "Natufarma"},
        ]
        svc.catalog.repo.save_snapshot("TIENDANUBE", tn)
        save_api_catalog(svc, ec)
        report = svc.report()
        ids = [c["ecomm_id"] for c in report["items"][0]["candidates"]]
        assert "vainilla" in ids
        assert "chocolate" not in ids
        assert svc.catalog.repo.snapshot("TIENDANUBE") == tn
        assert len(svc.catalog.repo.snapshot("ECOMM_APP_API_STAGE")) == 1
