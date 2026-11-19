"""A reviewed 20-URL manifest persists without scraping or approvals.

Every test uses synthetic catalog data and a disposable coordination table.
The import stub stores an original flagged PENDING; nothing contacts providers,
changes stock or prepares public channel publication.
"""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import CatalogSnapshot, EcommApiProductEdit
from app.services.documental.storage import Document, Dossier, digest
from app.services.documental.source_intake_queue import SourceIntakeQueue
from app.services.documental.source_intake_storage import (
    SourceIntakeBase, SourceIntakeJob,
)
from test_documental_manufacturer_batch_intake import (
    FIRST, SECOND, HOST, prepare_two,
)
from test_documental_complete_draft_flow import IDENT


def setup(tmp_path):
    engine = prepare_two(tmp_path)
    SourceIntakeBase.metadata.create_all(engine)
    return engine


def entries():
    return [
        {"ecomm_id": IDENT, "url": FIRST,
         "provenance_note": "Página de la variante revisada contra Ecomm-App."},
        {"ecomm_id": "9912345", "url": SECOND,
         "provenance_note": "Segunda variante cotejada por el operador."},
    ]


def fake_importer(db, session, *, ecomm_id, expected_version, reference_url,
                  provenance_note, configured_hosts):
    assert configured_hosts == HOST
    assert expected_version == 0
    assert "operador" in provenance_note or "Ecomm-App" in provenance_note
    ident = "local-" + ("f" if ecomm_id == IDENT else "e") * 32
    body = {
        "associated_ecomm_id": ecomm_id,
        "source": {
            "reference_url": reference_url,
            "review_state": "PENDING",
            "declared_official": False,
        },
        "synthetic": True,
    }
    db.add(Document(id=ident, version=1, body=body,
                    digest=digest(body), history=[]))
    db.commit()
    return {"incorporated_document_id": ident}


def test_stage_without_provider_requests_and_resume_on_new_session(tmp_path):
    engine = setup(tmp_path)
    with Session(engine) as db:
        q = SourceIntakeQueue(db, SimpleNamespace(id=1), HOST)
        ticket = q.create_explicit(str(uuid4()), entries())
        assert ticket["selection_mode"] == "EXACT_OPERATOR_URL"
        assert ticket["total"] == 2
        assert ticket["counts"]["PENDING"] == 2
        assert ticket["claims_approved"] == 0
        assert ticket["external_writes_enabled"] is False
        assert ticket["manual_steps_only"] is True
        assert not db.scalars(select(Document)).all()
        first = q.step(ticket["id"], ticket["revision"],
                       explicit_importer=fake_importer,
                       importer=lambda *_a, **_k: pytest.fail("No sitemap"))
        assert first["counts"]["IMPORTED"] == 1
        assert first["counts"]["PENDING"] == 1
        assert first["items"][0]["document_id"]
    with Session(engine) as db:
        q = SourceIntakeQueue(db, SimpleNamespace(id=2), HOST)
        progress = q.detail(ticket["id"])
        final = q.step(ticket["id"], progress["revision"],
                       explicit_importer=fake_importer,
                       importer=lambda *_a, **_k: pytest.fail("No sitemap"))
        assert final["state"] == "COMPLETED"
        assert final["counts"]["IMPORTED"] == 2
        assert len(db.scalars(select(Document)).all()) == 2
        assert db.scalars(select(EcommApiProductEdit)).all() == []
        assert db.scalars(select(Dossier)).all() == []


def test_idempotency_rejects_same_key_changed_url_or_provenance(tmp_path):
    engine = setup(tmp_path)
    with Session(engine) as db:
        q = SourceIntakeQueue(db, SimpleNamespace(id=1), HOST)
        key = str(uuid4())
        created = q.create_explicit(key, entries())
        assert q.create_explicit(key, entries())["id"] == created["id"]
        changed = deepcopy(entries())
        changed[0]["provenance_note"] = "Texto de revisión diferente del operador."
        with pytest.raises(ValueError, match="otro lote"):
            q.create_explicit(key, changed)
        assert len(db.scalars(select(SourceIntakeJob)).all()) == 1


@pytest.mark.parametrize("change", [
    "duplicate", "different-host", "query", "missing-note", "unselected-id",
])
def test_manifest_is_rejected_before_network_or_db_write(tmp_path, change):
    engine = setup(tmp_path)
    rows = entries()
    if change == "duplicate":
        rows[1]["ecomm_id"] = IDENT
    elif change == "different-host":
        rows[1]["url"] = "https://otro-fabricante.invalid/producto/"
    elif change == "query":
        rows[0]["url"] = FIRST + "?utm_source=tracker"
    elif change == "missing-note":
        rows[0]["provenance_note"] = "corto"
    elif change == "unselected-id":
        rows[0]["ecomm_id"] = "999999999"
    with Session(engine) as db:
        q = SourceIntakeQueue(
            db, SimpleNamespace(id=1),
            HOST + ",otro-fabricante.invalid",
        )
        with pytest.raises(ValueError):
            q.create_explicit(str(uuid4()), rows)
        assert db.scalars(select(SourceIntakeJob)).all() == []
        assert db.scalars(select(Document)).all() == []


def test_changed_identity_blocks_before_exact_url_fetch(tmp_path):
    engine = setup(tmp_path)
    with Session(engine) as db:
        q = SourceIntakeQueue(db, SimpleNamespace(id=1), HOST)
        ticket = q.create_explicit(str(uuid4()), [entries()[0]])
        stage = db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        ))
        payload = deepcopy(stage.payload)
        payload[0]["items"][0]["variants"][0]["sku"] = "OTRO-SKU"
        stage.payload = payload
        db.commit()
        blocked = q.step(ticket["id"], ticket["revision"],
                         explicit_importer=lambda *_a, **_k: pytest.fail("No GET"))
        assert blocked["state"] == "NEEDS_REVIEW"
        assert blocked["items"][0]["state"] == "BLOCKED"
        assert blocked["items"][0]["attempts"] == 0


def test_failed_fetch_blocks_only_one_item_and_retry_preserves_other(tmp_path):
    engine = setup(tmp_path)
    with Session(engine) as db:
        q = SourceIntakeQueue(db, SimpleNamespace(id=1), HOST)
        ticket = q.create_explicit(str(uuid4()), entries())
        def rejected(*_args, **_kwargs):
            raise ValueError("robots.txt bloquea el producto")
        failed = q.step(ticket["id"], ticket["revision"],
                        explicit_importer=rejected)
        assert failed["counts"]["BLOCKED"] == 1
        assert failed["counts"]["PENDING"] == 1
        next_step = q.step(ticket["id"], failed["revision"],
                           explicit_importer=fake_importer)
        assert next_step["counts"]["IMPORTED"] == 1
        retried = q.retry(ticket["id"], next_step["revision"], IDENT)
        assert retried["counts"]["PENDING"] == 1
        assert retried["items"][0]["attempts"] == 1
        end = q.step(ticket["id"], retried["revision"],
                     explicit_importer=fake_importer)
        assert end["counts"]["IMPORTED"] == 2
        assert end["items"][0]["attempts"] == 2


def test_empty_db_has_no_implicit_migration_and_flag_is_required(tmp_path, monkeypatch):
    from fastapi import HTTPException
    import app.api.routes.documental_workspace as routes

    engine = prepare_two(tmp_path)
    settings = SimpleNamespace(
        kiki_document_resumable_intake_enabled=False,
        kiki_document_batch_source_import_enabled=False,
        kiki_document_sitemap_discovery_enabled=False,
        kiki_document_explicit_url_intake_enabled=True,
        kiki_document_parser_kernel_required=True,
        kiki_document_source_fetch_hosts=HOST,
    )
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    monkeypatch.setattr(routes, "reader_available", lambda: True)
    with Session(engine) as db:
        with pytest.raises(HTTPException) as error:
            routes._resumable_intake_ready(db)
        assert error.value.status_code == 403
        settings.kiki_document_resumable_intake_enabled = True
        with pytest.raises(HTTPException) as missing:
            routes._resumable_intake_ready(db)
        assert missing.value.status_code == 503
        # Test setup is the only place that applies DDL.
        SourceIntakeBase.metadata.create_all(engine)
        assert routes._resumable_intake_ready(db) is settings
