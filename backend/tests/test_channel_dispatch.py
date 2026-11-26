import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.services.channel_dispatch import (
    DispatchConflict, begin, confirm, mark_unknown, read_receipt, reserve,
)
from app.services.channel_dispatch_storage import ChannelDispatchBase


@pytest.fixture
def engine():
    db = create_engine("sqlite://")
    ChannelDispatchBase.metadata.create_all(db)
    yield db
    db.dispose()


def reservation(db, **overrides):
    params = dict(channel="tn", store_id="123", ecomm_id="456",
                  sku="ABC", fingerprint="a" * 64, actor="operator")
    return reserve(db, **{**params, **overrides})


def test_duplicate_sku_and_identity(engine):
    with Session(engine) as db:
        ident = reservation(db)
    with Session(engine) as db:
        with pytest.raises(DispatchConflict):
            reservation(db, ecomm_id="789", sku=" abc ")
        with pytest.raises(DispatchConflict):
            reservation(db, sku="NEW")
        other = reservation(db, channel="ml")
        assert other != ident


def test_compare_and_swap_and_confirm(engine):
    with Session(engine) as db:
        ident = reservation(db)
        assert begin(db, ident, 1) == 2
    with Session(engine) as db:
        with pytest.raises(DispatchConflict):
            begin(db, ident, 1)
        assert confirm(db, ident, 2, "987") == 3
    with Session(engine) as db:
        receipt = read_receipt(db, ident)
        assert receipt["state"] == "CONFIRMED"
        assert receipt["remote_id"] == "987"
        with pytest.raises(DispatchConflict):
            confirm(db, ident, 2, "654")


def test_uncertain_result_remains_blocked(engine):
    with Session(engine) as db:
        ident = reservation(db)
        begin(db, ident, 1)
        mark_unknown(db, ident, 2)
    with Session(engine) as db:
        assert read_receipt(db, ident)["state"] == "UNKNOWN"
        with pytest.raises(DispatchConflict):
            reservation(db)
        with pytest.raises(DispatchConflict):
            begin(db, ident, 3)
        with pytest.raises(DispatchConflict):
            confirm(db, ident, 3, "987")


def test_inflight_survives_interruption(engine):
    with Session(engine) as db:
        ident = reservation(db)
        begin(db, ident, 1)
    with Session(engine) as db:
        assert read_receipt(db, ident)["state"] == "IN_FLIGHT"
        with pytest.raises(DispatchConflict):
            reservation(db)


def test_invalid_fingerprint(engine):
    with Session(engine) as db:
        with pytest.raises(ValueError):
            reservation(db, fingerprint="not-a-fingerprint")
