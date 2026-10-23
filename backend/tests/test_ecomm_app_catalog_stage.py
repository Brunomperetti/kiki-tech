"""Resumable catalog staging must not overwrite production snapshots."""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.models import Base, CatalogSnapshot
from app.integrations.ecomm_app.public_api import API_PREFIX, EcommAppApiError
from app.integrations.ecomm_app.catalog_stage import (
    EcommAppStageService, STAGE_SOURCE, _extend, _source_page, stage_status,
)


def fake_page(page, *, total=201):
    first = (page-1)*50
    end = min(first+50, total)
    return {
        "items": [{
            "code": f"P-{i}",
            "description": f"Product {i}",
            "is_combo": i % 9 == 0,
            "total_stock": 0,
            "variants": [{
                "id": i + 2000,
                "sku": f"V-{i}",
                "total_stock": 0,
                "is_combo": i % 9 == 0,
                "warehouses": [{"id": 2210, "stock": 0}],
            }],
        } for i in range(first, end)],
        "paginacion": {
            "page": page,
            "per_page": 50,
            "total": total,
            "total_pages": (total+49)//50,
        },
    }


class StubClient:
    def __init__(self, *, total=201, failure=None):
        self.total = total
        self.failure = failure
        self.calls = []

    def _call(self, method, path, *, params=None, body=None):
        assert method == "GET"
        assert path == f"{API_PREFIX}/productos"
        assert body is None
        assert params["sort"] == "sku_asc"
        assert params["limit"] == 50
        page = params["page"]
        self.calls.append(page)
        if self.failure is not None and page == self.failure:
            raise EcommAppApiError(503, "SIN_CONEXION", "Sin respuesta")
        return fake_page(page, total=self.total)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(CatalogSnapshot(source="ECOMM_APP", payload=[{"original": "DO-NOT-CHANGE"}]))
        session.add(CatalogSnapshot(source="ECOMM_APP_RAW", payload=[{"original": "DO-NOT-CHANGE"}]))
        session.commit()
        yield session
    engine.dispose()


def test_first_batch_saves_only_three_pages_and_leaves_existing_inventory(db):
    client = StubClient(total=201)
    status = EcommAppStageService(db, client).next_batch()
    assert client.calls == [1, 2, 3]
    assert status["pages_saved"] == 3
    assert status["next_page"] == 4
    assert status["expected_pages"] == 5
    assert status["expected_parents"] == 201
    assert status["quality"]["parents"] == 150
    assert status["quality"]["variants"] == 150
    assert status["quality"]["without_total_stock"] == 0
    assert status["complete"] is False
    assert db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP")).payload == [{"original": "DO-NOT-CHANGE"}]
    assert db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP_RAW")).payload == [{"original": "DO-NOT-CHANGE"}]


def test_resume_from_next_page_and_stops_at_real_end(db):
    client = StubClient(total=201)
    service = EcommAppStageService(db, client)
    service.next_batch()
    done = service.next_batch()
    assert client.calls == [1, 2, 3, 4, 5]
    assert done["complete"] is True
    assert done["pages_saved"] == 5
    assert done["expected_parents"] == 201
    assert done["quality"]["parents"] == 201
    assert done["quality"]["variants"] == 201
    assert done["next_page"] is None
    assert len(db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE)).payload) == 5
    service.next_batch()
    assert client.calls == [1, 2, 3, 4, 5]


def test_failed_batch_does_not_destroy_prior_persisted_pages(db):
    client = StubClient(total=201)
    service = EcommAppStageService(db, client)
    service.next_batch()
    client.failure = 4
    with pytest.raises(EcommAppApiError):
        service.next_batch()
    unchanged = service.status()
    assert unchanged["pages_saved"] == 3
    assert unchanged["quality"]["parents"] == 150
    client.failure = None
    result = service.next_batch()
    assert result["complete"]
    assert client.calls[-2:] == [4, 5]


def test_vendor_total_drift_blocks_batch_and_keeps_prior_stage(db):
    client = StubClient(total=201)
    service = EcommAppStageService(db, client)
    service.next_batch()
    client.total = 202
    with pytest.raises(EcommAppApiError) as exc:
        service.next_batch()
    assert exc.value.code == "CATALOGO_CAMBIO"
    assert service.status()["pages_saved"] == 3


def test_duplicate_variant_id_blocks_batch_even_across_pages():
    pages = [_source_page(fake_page(1, total=101), 1, None)]
    dup = fake_page(2, total=101)
    dup["items"][0]["variants"][0]["id"] = 2000
    with pytest.raises(EcommAppApiError) as exc:
        _extend(pages, [dup])
    assert exc.value.code == "ID_VARIANTE_REPETIDO"
    assert len(pages) == 1


def test_incomplete_page_or_bad_pagination_never_looks_like_full_inventory():
    broken = fake_page(1, total=121)
    broken["items"].pop()
    with pytest.raises(EcommAppApiError, match="esperada"):
        _source_page(broken, 1, None)
    missing_meta = {"items": [{"code": "A"}]}
    with pytest.raises(EcommAppApiError) as exc:
        _source_page(missing_meta, 1, None)
    assert exc.value.code == "SIN_PAGINACION"


def test_status_without_stage_is_empty_not_a_false_complete():
    s = stage_status([])
    assert not s["exists"]
    assert not s["complete"]
    assert s["pages_saved"] == 0
    assert s["can_continue"]
