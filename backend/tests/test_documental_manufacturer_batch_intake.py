"""Regression for operator-confirmed, sitemap-matched manufacturer intake.

No live network, no AI, no customer database, no publishing.
"""
import hashlib
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import CatalogSnapshot
from app.services.documental.manufacturer_batch_intake import (
    capture_selected, preflight,
)
from app.services.documental.storage import Document
from document_reader.parser import parse
from test_documental_complete_draft_flow import IDENT, prepare
from test_documental_saved_page_html import saved_page


HASH = "a" * 64
SITEMAP = "https://naturalseed.com.ar/product-sitemap.xml"
FIRST = "https://naturalseed.com.ar/producto/mix-ensaladas-y-sopas/"
SECOND = "https://naturalseed.com.ar/producto/galletas-200g/"
HOST = "naturalseed.com.ar"


def candidate(ident, url, *, ambiguous=False, count=1):
    return {
        "ecomm_id": ident,
        "sku": "9995" if ident == IDENT else "9996",
        "name": "Producto de fabricante",
        "state": "CANDIDATES",
        "ambiguous": ambiguous,
        "candidate_count": count,
        "candidates": [
            {"url": url, "verified": False, "review_required": True},
        ],
    }


def preview(*items, sha=HASH):
    return {"receipt": {"sitemap_sha256": sha}, "items": list(items)}


def fake_source(url, hosts, *, max_bytes):
    assert hosts == HOST and max_bytes == 4 * 1024 * 1024
    assert url in {FIRST, SECOND}
    body = (saved_page() if url == FIRST else """<html><main>
        <h1>Galletas 200 g</h1><p>Presentación: 200 g</p>
    </main></html>""").encode()
    return body, {
        "sha256": hashlib.sha256(body).hexdigest(),
        "size": len(body), "host": HOST, "requested_url": url,
        "final_url": url, "robots_checked": True,
        "tls_hostname_verified": True, "network_enabled": True,
        "redirects_followed": 0,
    }


def parse_source(body):
    return parse(
        body.filename, body.content_type, body.content_base64,
        web_snapshot=body.web_snapshot,
    )


def prepare_two(tmp_path):
    engine, original = prepare(tmp_path)
    with Session(engine) as db:
        snap = db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE",
        ))
        stage = deepcopy(snap.payload)
        stage[0]["items"].append({
            "code": "9996", "description": "Galletas 200 g",
            "is_combo": False,
            "variants": [{
                "id": 9912345, "sku": "9996", "is_combo": False,
                "description": "Galletas 200 g",
                "variant_description": "200 g",
                "gtin": None, "barcode": None, "total_stock": 1,
            }],
        })
        snap.payload = stage
        db.commit()
    return engine


@pytest.mark.parametrize("change", [
    {"sha": "0" * 64},
    {"url": SECOND},
    {"ambiguous": True},
    {"count": 2},
])
def test_preflight_blocks_changed_sitemap_and_ambiguous_urls(change):
    entry = candidate(IDENT, FIRST, ambiguous=change.get("ambiguous", False),
                      count=change.get("count", 1))
    body = {"ecomm_id": IDENT, "url": change.get("url", FIRST)}
    with pytest.raises(ValueError):
        preflight(preview(entry, sha=change.get("sha", HASH)), [body], HASH)


def test_two_sources_are_archived_atomically_as_pending_evidence(tmp_path, monkeypatch):
    import app.services.documental.research as module

    monkeypatch.setattr(
        module, "get_settings", lambda: SimpleNamespace(kiki_admin_username="test"),
    )
    engine = prepare_two(tmp_path)
    items = [{"ecomm_id": IDENT, "url": FIRST},
             {"ecomm_id": "9912345", "url": SECOND}]
    calls = []
    with Session(engine) as db:
        result = capture_selected(
            db, SimpleNamespace(id=1),
            sitemap_url=SITEMAP, sitemap_sha256=HASH,
            items=items, configured_hosts=HOST,
            previewer=lambda _db, ids, sitemap, host: (
                calls.append("sitemap") or
                preview(*(candidate(x, item["url"]) for x, item in zip(ids, items)))
            ),
            downloader=lambda *args, **kwargs: (
                calls.append(args[0]) or fake_source(*args, **kwargs)
            ),
            parser=parse_source,
        )
        assert calls == ["sitemap", FIRST, SECOND]
        assert result["originals_archived"] == 2
        assert result["facts_approved"] == 0
        assert result["external_catalogue_writes"] == 0
        assert result["openai_requests"] == 0

    with Session(engine) as db:
        for entry in result["documents"]:
            doc = db.get(Document, entry["document_id"])
            assert doc.body["associated_ecomm_id"] == entry["ecomm_id"]
            assert doc.body["source"]["review_state"] == "PENDING"
            assert doc.body["source"]["declared_official"] is False
            assert doc.body["retrieval"]["sitemap_sha256"] == HASH
            assert doc.body["retrieval"]["tls_hostname_verified"] is True
            assert doc.body["retrieval"]["mode"] == "ALLOWLISTED_EXPLICIT_BATCH"
            assert entry["facts_approved"] == 0
        assert db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        )).payload[0]["items"][0]["variants"][0]["sku"] == "9995"


def test_parser_failure_never_archives_partial_batch(tmp_path, monkeypatch):
    import app.services.documental.research as module
    monkeypatch.setattr(
        module, "get_settings", lambda: SimpleNamespace(kiki_admin_username="test"),
    )
    engine = prepare_two(tmp_path)
    items = [{"ecomm_id": IDENT, "url": FIRST},
             {"ecomm_id": "9912345", "url": SECOND}]
    processed = []

    def broken_parser(body):
        processed.append(body.reference_url)
        if len(processed) == 2:
            raise ValueError("Fuente sin texto legible")
        return parse_source(body)

    with Session(engine) as db:
        with pytest.raises(ValueError, match="texto legible"):
            capture_selected(
                db, SimpleNamespace(id=1),
                sitemap_url=SITEMAP, sitemap_sha256=HASH,
                items=items, configured_hosts=HOST,
                previewer=lambda _db, ids, *_: preview(
                    *(candidate(ident, url) for ident, url in zip(ids, [FIRST, SECOND]))
                ),
                downloader=fake_source, parser=broken_parser,
            )
        db.rollback()

    with Session(engine) as db:
        # prepare() already stores one unrelated fictional test document.
        docs = db.scalars(select(Document)).all()
        assert len(docs) == 1
        assert all(
            doc.body["source"]["reference_url"] not in {FIRST, SECOND}
            for doc in docs
        )


def test_route_is_default_off_and_never_calls_external_io(tmp_path, monkeypatch):
    import app.api.routes.documental_workspace as route
    from app.api.routes.documental_workspace import (
        ManufacturerBatchRequest, ManufacturerBatchItem,
    )
    engine, _ = prepare(tmp_path)
    opts = SimpleNamespace(
        kiki_document_parser_kernel_required=True,
        kiki_document_batch_source_import_enabled=False,
        kiki_document_sitemap_discovery_enabled=True,
        kiki_document_source_fetch_hosts=HOST,
    )
    monkeypatch.setattr(route, "get_settings", lambda: opts)
    monkeypatch.setattr(route, "reader_available", lambda: True)
    monkeypatch.setattr(route, "capture_selected",
                        lambda *_args, **_kwargs: pytest.fail("IO forbidden"))
    payload = ManufacturerBatchRequest(
        sitemap_url=SITEMAP, sitemap_sha256=HASH,
        items=[ManufacturerBatchItem(ecomm_id=IDENT, url=FIRST)],
        authorized_local_processing=True, confirm=True,
    )
    with Session(engine) as db:
        with pytest.raises(HTTPException) as err:
            route.import_manufacturer_batch(payload, db, SimpleNamespace(id=1))
    assert err.value.status_code == 403


def test_no_reads_for_oversized_or_repeated_selection(tmp_path):
    engine, _ = prepare(tmp_path)
    entries = [{"ecomm_id": IDENT, "url": FIRST}] * 2
    with Session(engine) as db:
        with pytest.raises(ValueError, match="repetir Ecomm ID"):
            capture_selected(
                db, SimpleNamespace(id=1),
                sitemap_url=SITEMAP, sitemap_sha256=HASH,
                items=entries, configured_hosts=HOST,
                previewer=lambda *_: pytest.fail("No sitemap GET"),
                downloader=lambda *_args, **_kwargs: pytest.fail("No HTML GET"),
            )
        with pytest.raises(ValueError, match="una o dos"):
            capture_selected(
                db, SimpleNamespace(id=1),
                sitemap_url=SITEMAP, sitemap_sha256=HASH,
                items=entries + entries[0:1], configured_hosts=HOST,
                previewer=lambda *_: pytest.fail("No sitemap GET"),
                downloader=lambda *_args, **_kwargs: pytest.fail("No HTML GET"),
            )
