"""No-sitemap exact URL intake regression.

Synthetic pages, disposable SQLite, no network, provider or AI calls.
This does not certify a manufacturer's identity or approve any fact.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import CatalogSnapshot, EcommApiProductEdit
from app.services.documental.explicit_url_intake import import_explicit_url
from app.services.documental.storage import Document, Dossier
from document_reader.parser import parse
from test_documental_complete_draft_flow import IDENT, prepare
from test_documental_saved_page_html import saved_page


URL = "https://naturalseed.com.ar/producto/mix-ensaladas-y-sopas/"
ALT = "https://naturalseed.com.ar/producto/mix-de-semillas/"
HOST = "naturalseed.com.ar"
HTML = saved_page().encode("utf-8")


def fake_downloader(url, hosts, *, max_bytes):
    assert url in {URL, ALT}
    assert hosts == HOST
    assert max_bytes == 4 * 1024 * 1024
    return HTML, {
        "sha256": sha256(HTML).hexdigest(),
        "size": len(HTML),
        "requested_url": url,
        "final_url": url,
        "host": HOST,
        "robots_checked": True,
        "tls_hostname_verified": True,
        "redirects_followed": 0,
        "network_enabled": True,
        "simulated": False,
        "acquired_at": datetime.now(timezone.utc).isoformat(),
    }


def fake_parser(body):
    return parse(
        body.filename, body.content_type, body.content_base64,
        web_snapshot=body.web_snapshot,
    )


def setup(tmp_path, monkeypatch):
    import app.services.documental.research as research_module
    monkeypatch.setattr(
        research_module, "get_settings",
        lambda: SimpleNamespace(kiki_admin_username="test"),
    )
    return prepare(tmp_path)[0]


def kwargs(**overrides):
    return {
        "ecomm_id": IDENT,
        "expected_version": 0,
        "reference_url": URL,
        "provenance_note": "Página exacta seleccionada para contrastar con Ecomm-App.",
        "configured_hosts": HOST,
        "downloader": fake_downloader,
        "parser": fake_parser,
        **overrides,
    }


def test_exact_source_stores_pending_original_with_provenance_and_no_edits(
    tmp_path, monkeypatch,
):
    engine = setup(tmp_path, monkeypatch)
    with Session(engine) as db:
        result = import_explicit_url(
            db, SimpleNamespace(id=1), **kwargs()
        )
        doc = db.get(Document, result["incorporated_document_id"])
        assert doc.body["associated_ecomm_id"] == IDENT
        assert doc.body["source"]["reference_url"] == URL
        assert doc.body["source"]["review_state"] == "PENDING"
        assert doc.body["source"]["declared_official"] is False
        assert doc.body["retrieval"]["mode"] == "ALLOWLISTED_EXPLICIT_OPERATOR_URL"
        assert doc.body["retrieval"]["selection_mode"] == "ONE_EXACT_OPERATOR_REVIEWED_URL"
        assert doc.body["original"]["sha256"] == sha256(HTML).hexdigest()
        assert doc.body["retrieval"]["robots_checked"] is True
        assert doc.body["retrieval"]["tls_hostname_verified"] is True
        assert result["facts"] == []
        assert db.scalars(select(EcommApiProductEdit)).all() == []
        assert db.scalar(select(Dossier.version).where(Dossier.ecomm_id == IDENT)) == result["version"]


def test_repeat_url_and_same_day_second_url_do_not_repeat_network(tmp_path, monkeypatch):
    engine = setup(tmp_path, monkeypatch)
    with Session(engine) as db:
        first = import_explicit_url(db, SimpleNamespace(id=1), **kwargs())
        expected = first["version"]
        with pytest.raises(ValueError, match="ya está archivada"):
            import_explicit_url(
                db, SimpleNamespace(id=1),
                **kwargs(
                    expected_version=expected,
                    downloader=lambda *_args, **_kw: pytest.fail("No network"),
                ),
            )
        db.rollback()
        with pytest.raises(ValueError, match="descarga automatizada de hoy"):
            import_explicit_url(
                db, SimpleNamespace(id=1),
                **kwargs(
                    reference_url=ALT,
                    expected_version=expected,
                    downloader=lambda *_args, **_kw: pytest.fail("No network"),
                ),
            )


def test_changed_ecomm_identity_during_fetch_blocks_original_storage(tmp_path, monkeypatch):
    engine = setup(tmp_path, monkeypatch)

    def change_during_network(url, hosts, *, max_bytes):
        with Session(engine) as other:
            stage = other.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
                )
            )
            payload = deepcopy(stage.payload)
            payload[0]["items"][0]["variants"][0]["sku"] = "SKU-CHANGED"
            stage.payload = payload
            other.commit()
        return fake_downloader(url, hosts, max_bytes=max_bytes)

    with Session(engine) as db:
        with pytest.raises(ValueError, match="cambió durante la consulta"):
            import_explicit_url(
                db, SimpleNamespace(id=1),
                **kwargs(downloader=change_during_network),
            )
        db.rollback()
    with Session(engine) as db:
        assert len(db.scalars(select(Document)).all()) == 1
        assert db.get(Dossier, IDENT) is None
        assert db.scalars(select(EcommApiProductEdit)).all() == []


@pytest.mark.parametrize("bad_url", [
    "http://naturalseed.com.ar/producto/mix-ensaladas-y-sopas/",
    "https://naturalseed.com.ar.evil.invalid/producto/",
    "https://naturalseed.com.ar/producto/?x=1",
    "https://127.0.0.1/admin",
])
def test_disallowed_url_fails_before_any_download(tmp_path, monkeypatch, bad_url):
    engine = setup(tmp_path, monkeypatch)
    with Session(engine) as db:
        with pytest.raises(ValueError, match="Fuente rechazada"):
            import_explicit_url(
                db, SimpleNamespace(id=1),
                **kwargs(
                    reference_url=bad_url,
                    downloader=lambda *_args, **_kw: pytest.fail("No download"),
                ),
            )


def test_failed_parser_or_robots_never_stores_a_new_document(tmp_path, monkeypatch):
    engine = setup(tmp_path, monkeypatch)
    with Session(engine) as db:
        with pytest.raises(ValueError, match="Lector falló"):
            import_explicit_url(
                db, SimpleNamespace(id=1),
                **kwargs(parser=lambda _: (_ for _ in ()).throw(
                    ValueError("Lector falló")
                )),
            )
        db.rollback()
        with pytest.raises(ValueError, match="robots.txt"):
            import_explicit_url(
                db, SimpleNamespace(id=1),
                **kwargs(downloader=lambda *_args, **_kw: (_ for _ in ()).throw(
                    ValueError("robots.txt denegó el acceso.")
                )),
            )
        db.rollback()
        assert len(db.scalars(select(Document)).all()) == 1
        assert db.get(Dossier, IDENT) is None


def test_route_requires_explicit_flag_and_isolated_reader(tmp_path, monkeypatch):
    import app.api.routes.documental_workspace as route
    from app.services.documental.contracts import ManufacturerFetch
    engine = setup(tmp_path, monkeypatch)
    config = SimpleNamespace(
        kiki_document_explicit_url_intake_enabled=False,
        kiki_document_parser_kernel_required=True,
        kiki_document_source_fetch_hosts=HOST,
    )
    monkeypatch.setattr(route, "get_settings", lambda: config)
    monkeypatch.setattr(route, "reader_available", lambda: True)
    monkeypatch.setattr(route, "import_explicit_url",
                        lambda *_args, **_kwargs: pytest.fail("No network"))
    body = ManufacturerFetch(
        expected_version=0, reference_url=URL,
        provenance_note="URL seleccionada expresamente para investigación.",
        authorized_local_processing=True,
    )
    with Session(engine) as db:
        with pytest.raises(HTTPException) as e:
            route.fetch_exact_reviewed_manufacturer_url(
                IDENT, body, db, SimpleNamespace(id=1)
            )
        assert e.value.status_code == 403
        config.kiki_document_explicit_url_intake_enabled = True
        monkeypatch.setattr(route, "reader_available", lambda: False)
        with pytest.raises(HTTPException) as e2:
            route.fetch_exact_reviewed_manufacturer_url(
                IDENT, body, db, SimpleNamespace(id=1)
            )
        assert e2.value.status_code == 403
