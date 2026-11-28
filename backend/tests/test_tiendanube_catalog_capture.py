import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.models import CatalogSnapshot
from app.services.tiendanube_catalog_capture import (
    SOURCE, compare_capture, read_catalog, refresh_catalog,
)


def product(pid, sku="SKU-A"):
    return {"id": pid, "name": {"es": f"Producto {pid}"}, "brand": "Marca",
            "visibility": "hidden", "published": False,
            "variants": [{"id": pid * 10, "sku": sku}]}


class Pages:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def catalog_page(self, page):
        self.calls.append(page)
        return self.pages[page - 1]


def test_complete_scan_exact_multiple_does_not_request_nonexistent_page():
    client = Pages([([product(i) for i in range(1, 101)], 100)])
    capture = read_catalog(client)
    assert capture["products"] == 100
    assert len(capture["rows"]) == 100
    assert client.calls == [1]


def test_empty_catalog_requires_explicit_zero_total():
    assert read_catalog(Pages([([], 0)]))["rows"] == []
    with pytest.raises(ValueError):
        read_catalog(Pages([([], 5)]))


def test_changed_total_and_repeated_product_fail_closed():
    first = [product(i) for i in range(1, 101)]
    with pytest.raises(ValueError):
        read_catalog(Pages([(first, 101), ([product(101)], 102)]))
    with pytest.raises(ValueError):
        read_catalog(Pages([(first, 101), ([product(1)], 101)]))


def test_duplicate_variant_id_and_missing_sku_field_fail_closed():
    bad = product(2)
    bad["variants"][0]["id"] = 10
    with pytest.raises(ValueError):
        read_catalog(Pages([([product(1), bad], 2)]))
    bad = product(2)
    del bad["variants"][0]["sku"]
    with pytest.raises(ValueError):
        read_catalog(Pages([([bad], 1)]))


def test_exact_sku_is_candidate_only_and_preserves_leading_zero():
    capture = read_catalog(Pages([([product(1, "001"), product(2, "1"),
                                   product(3, "DUP"), product(4, "dup"),
                                   product(5, "")], 5)]))
    master = {"a": {"sku": "001"}, "b": {"sku": "DUP"}, "c": {"sku": "missing"}}
    report = compare_capture(capture, master, "a")
    assert report["match_state"] == "UNIQUE_SKU_CANDIDATE"
    assert report["matches_total"] == 1
    assert report["matches"][0]["product_id"] == 1
    assert report["summary"]["DUPLICATE_TN"] == 2
    assert compare_capture(capture, master, "b")["match_state"] == "DUPLICATE_TN"
    assert compare_capture(capture, master, "c")["match_state"] == "NO_SKU_MATCH_IN_CAPTURE"
    master["d"] = {"sku": "001"}
    assert compare_capture(capture, master, "a")["match_state"] == "AMBIGUOUS_ECOMM"


def test_successful_refresh_is_separate_and_failed_refresh_preserves_capture():
    engine = create_engine("sqlite://")
    CatalogSnapshot.__table__.create(engine)
    settings = Settings(_env_file=None, kiki_tiendanube_read_enabled=True,
                        tiendanube_store_id="123", tiendanube_access_token="synthetic")

    def good(method, url, **kwargs):
        assert method == "GET"
        assert kwargs["include_total"] is True
        assert kwargs["headers"]["Authorization"] == "Bearer synthetic"
        return [product(1)], "1"

    def bad(*args, **kwargs):
        return [], "2"

    with Session(engine) as db:
        db.add(CatalogSnapshot(source="TIENDANUBE", payload=[{"sku": "old-csv"}]))
        db.commit()
        first = refresh_catalog(db, settings, transport=good)
        with pytest.raises(ValueError):
            refresh_catalog(db, settings, transport=bad)
        db.rollback()
        saved = {r.source: r.payload for r in db.scalars(select(CatalogSnapshot))}
        assert saved[SOURCE] == [first]
        assert saved["TIENDANUBE"] == [{"sku": "old-csv"}]
    engine.dispose()


@pytest.mark.parametrize("visibility", ["visible", "hidden", "unlisted"])
def test_documented_visibility_is_preserved(visibility):
    row = product(1)
    row["visibility"] = visibility
    row["published"] = visibility == "visible"
    capture = read_catalog(Pages([([row], 1)]))
    assert capture["rows"][0]["visibility"] == visibility
    assert capture["rows"][0]["published"] is (visibility == "visible")
