import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database.models import Base, TiendanubeMatchDecision
from app.services.tiendanube_assisted_match_service import TiendanubeAssistedMatchService

def test_bulk_approval_requires_exclusive_high_confidence_and_preserves_snapshots():
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc=TiendanubeAssistedMatchService(db)
        tn=[{"slug":"a","sku":"TN-X","name":"Avena Granix 400 gr","brand":"Granix"}]
        ec=[{"ecomm_id":"E1","sku":"EC-X","name":"Avena Granix 400 gr","brand":"Granix"}]
        svc.catalog.repo.save_snapshot("TIENDANUBE",tn)
        svc.catalog.repo.save_snapshot("ECOMM_APP",ec)
        key=svc.report()["items"][0]["source_key"]
        preview=svc.bulk_approve_preview([key])
        assert len(preview["eligible"])==1 and not preview["excluded"]
        assert svc.bulk_approve([key],"Verificado producto marca y tamaño")["updated"]==1
        assert db.query(TiendanubeMatchDecision).one().status=="APPROVED"
        assert svc.catalog.repo.snapshot("TIENDANUBE")==tn
        assert svc.catalog.repo.snapshot("ECOMM_APP")==ec
        with pytest.raises(ValueError):
            svc.bulk_approve([key],"No debe aprobarse nuevamente")

def test_bulk_approval_excludes_ambiguous_flavors_and_preexisting_decisions():
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc=TiendanubeAssistedMatchService(db)
        svc.catalog.repo.save_snapshot("TIENDANUBE",[{"slug":"v","sku":"TN Vainilla","name":"Vitaneral Natufarma HMB 240 g","brand":"Natufarma"}])
        svc.catalog.repo.save_snapshot("ECOMM_APP",[
            {"ecomm_id":"V","sku":"VITANERALVAINILLA","name":"Vitaneral Natufarma HMB 240 g","brand":"Natufarma"},
            {"ecomm_id":"C","sku":"VITANERALCHOCOLATE","name":"Vitaneral Natufarma HMB 240 g","brand":"Natufarma"}])
        key=svc.report()["items"][0]["source_key"]
        assert svc.bulk_approve_preview([key])["eligible"][0]["target_id"]=="V"
        svc.decide(key,"V","APPROVED","Verifiqué la presentación")
        assert svc.bulk_approve_preview([key])["excluded"]
        with pytest.raises(ValueError):
            svc.bulk_approve([key],"No volver a aprobar")
        with pytest.raises(ValueError):
            svc.bulk_approve_preview([key,key])
