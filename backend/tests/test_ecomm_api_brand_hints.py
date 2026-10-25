"""Evidence-led brand hints do not use historical Ecomm inventory or write channels."""
from copy import deepcopy

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import Base, CatalogSnapshot, EcommApiProductEdit
from app.services.ecomm_api_brand_hints_service import EcommApiBrandHints
from test_ecomm_api_product_workspace import capture


def make_db(tmp_path, tn=None, ml=None, stage=None):
    engine = create_engine("sqlite:///" + str(tmp_path / "brands.db"))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for source, data in [
            ("ECOMM_APP_API_STAGE", stage or capture()),
            ("TIENDANUBE", tn or []), ("MERCADOLIBRE_API", ml or []),
            ("ECOMM_APP", [{"ecomm_id": "101", "sku": "2500",
                            "brand": "Do not use historical data"}]),
        ]:
            db.add(CatalogSnapshot(source=source, payload=data))
        db.commit()
    return engine


def test_tn_exact_unique_sku_produces_reviewable_brand_not_a_write(tmp_path):
    tn=[{"slug":"v1","sku":"2500","name":"Magnesio con Potasio 30 cápsulas","brand":"Vitamin Way"}]
    engine=make_db(tmp_path,tn=tn)
    with Session(engine) as db:
        report=EcommApiBrandHints(db).get("101")
        assert report["status"]=="EVIDENCE_FOUND"
        assert report["brand"]=="Vitamin Way"
        assert report["evidence"][0]["channel"]=="TIENDANUBE_CSV"
        assert report["external_writes_enabled"] is False
        assert not db.scalars(select(EcommApiProductEdit)).all()
        assert db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source=="TIENDANUBE")).payload==tn


def test_disagreeing_channels_do_not_suggest_a_brand(tmp_path):
    engine=make_db(
        tmp_path,
        tn=[{"slug":"v1","sku":"2500","name":"Magnesio con Potasio 30 cápsulas","brand":"Brand A"}],
        ml=[{"external_id":"MLA123","sku_product":"2500",
             "title":"Magnesio con Potasio 30 cápsulas","brand":"Brand B"}],
    )
    with Session(engine) as db:
        report=EcommApiBrandHints(db).get("101")
        assert report["status"]=="CONFLICT"
        assert report["brand"] is None
        assert len(report["evidence"])==2


def test_combo_not_deduced_from_family_prefix_and_missing_brand_fails_closed(tmp_path):
    engine=make_db(tmp_path,ml=[
        {"external_id":"MLA102","sku":"2500","brand":"Example",
         "title":"Magnesio con Potasio 30 cápsulas"},
    ])
    with Session(engine) as db:
        report=EcommApiBrandHints(db).get("102")
        assert report["status"]=="NO_EVIDENCE"
        assert report["brand"] is None
        # The historical Ecomm record happens to have the right SKU for 101,
        # but historical brands are deliberately never considered.
        report2=EcommApiBrandHints(db).get("101")
        assert report2["brand"]=="Example"


def test_duplicate_api_variant_sku_and_multiple_tn_products_block_hint(tmp_path):
    stage=deepcopy(capture())
    stage[0]["items"][1]["variants"][0]["sku"]="2500"
    engine=make_db(tmp_path,stage=stage,tn=[
        {"slug":"a","sku":"2500","brand":"Vitamin"},
    ])
    with Session(engine) as db:
        assert EcommApiBrandHints(db).get("101")["status"]=="AMBIGUOUS_API_SKU"

    engine2=make_db(tmp_path/"another",tn=[
        {"slug":"a","sku":"2500","brand":"Brand"}, {"slug":"b","sku":"2500","brand":"Brand"}
    ])
    with Session(engine2) as db:
        row=EcommApiBrandHints(db).get("101")
        assert row["status"]=="CONFLICT" and row["brand"] is None


def test_ml_variation_without_own_sku_cannot_borrow_parent_product_sku(tmp_path):
    engine=make_db(tmp_path,ml=[{
        "external_id":"MLA100#456","sku_product":"2500","brand":"Unreliable",
        "title":"Magnesio con Potasio 30 cápsulas",
    }])
    with Session(engine) as db:
        assert EcommApiBrandHints(db).get("101")["status"]=="NO_EVIDENCE"
