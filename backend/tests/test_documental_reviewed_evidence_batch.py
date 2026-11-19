"""Bulk re-extraction of reviewed originals never approves claims or edits products.

Uses isolated SQLite and a fictional HTML fixture. No manufacturer fetch,
real customer data, AI or external publication.
"""
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import EcommApiProductEdit, KikiAiEditorialDraft
from app.services.documental.local_documents import LocalDocuments, parse_local
from app.services.documental.contracts import Provenance
from app.services.documental.reextract_reviewed_batch import (
    extract_reviewed_selection,
)
from app.services.documental.storage import Dossier
from test_documental_complete_draft_flow import IDENT, prepare
from test_documental_saved_page_import import upload_payload


def setup(tmp_path, monkeypatch):
    import app.services.documental.research as research_module
    monkeypatch.setattr(
        research_module, "get_settings",
        lambda: SimpleNamespace(kiki_admin_username="test"),
    )
    return prepare(tmp_path)[0]


def attach_reviewed_real_original(db, user):
    service = LocalDocuments(db, user)
    body = upload_payload()
    parsed = parse_local(body)
    uploaded = service.incorporate(IDENT, body, parsed)
    doc_id = uploaded["incorporated_document_id"]
    doc = service.research._document(doc_id)
    checked = service.provenance(
        IDENT, doc_id, Provenance(
            expected_document_version=doc.version, decision="REVIEWED",
            reason="Fuente ficticia revisada en base descartable de pruebas.",
        ),
    )
    return service, checked, doc_id


def test_no_reviewed_real_original_never_adds_facts(tmp_path, monkeypatch):
    engine = setup(tmp_path, monkeypatch)
    with Session(engine) as db:
        user = SimpleNamespace(id=1)
        report = extract_reviewed_selection(db, user, [IDENT])
        assert report["total"] == 1
        assert report["counts"] == {"PREPARED": 0, "NO_CHANGES": 0, "BLOCKED": 1}
        assert report["human_fact_approval_required"] is True
        assert report["facts_approved_by_operation"] == 0
        assert report["provider_calls"] == report["ai_requests"] == 0
        assert report["automatic_publications"] == 0
        assert db.scalars(select(EcommApiProductEdit)).all() == []
        assert db.scalars(select(KikiAiEditorialDraft)).all() == []


def test_unreviewed_or_name_mismatched_source_blocks_before_alias(tmp_path, monkeypatch):
    engine = setup(tmp_path, monkeypatch)
    user = SimpleNamespace(id=1)
    with Session(engine) as db:
        svc = LocalDocuments(db, user)
        body = upload_payload()
        imported = svc.incorporate(IDENT, body, parse_local(body))
        status = extract_reviewed_selection(db, user, [IDENT])
        assert status["items"][0]["state"] == "BLOCKED"
        assert "original real revisado" in status["items"][0]["reasons"][0]
        doc_id = imported["incorporated_document_id"]
        doc = svc.research._document(doc_id)
        svc.provenance(IDENT, doc_id, Provenance(
            expected_document_version=doc.version, decision="REVIEWED",
            reason="Fuente ficticia revisada para ensayo aislado en SQLite.",
        ))
        pending = extract_reviewed_selection(db, user, [IDENT])
        assert pending["counts"]["BLOCKED"] == 1
        assert any("Nombre incompatible" in reason for reason in pending["items"][0]["reasons"])
        assert db.scalars(select(KikiAiEditorialDraft)).all() == []


def test_alias_review_then_bulk_extraction_only_creates_pending_facts(tmp_path, monkeypatch):
    engine = setup(tmp_path, monkeypatch)
    user = SimpleNamespace(id=1)
    with Session(engine) as db:
        service, reviewed, document_id = attach_reviewed_real_original(db, user)
        latest = service.research._document(document_id)
        identity = service.research.review_document_identity(
            IDENT, reviewed["version"], document_id, latest.version,
            "APPROVED", "Cotejé identidad y presentación del HTML ficticio contra el SKU.",
        )
        result = extract_reviewed_selection(db, user, [IDENT])
        assert result["counts"] == {"PREPARED": 1, "NO_CHANGES": 0, "BLOCKED": 0}
        assert result["items"][0]["document_id"] == document_id
        assert result["items"][0]["document_version"] == latest.version
        assert result["items"][0]["facts_pending"] == 3
        assert result["items"][0]["facts_approved_unchanged"] == 0
        assert result["facts_approved_by_operation"] == 0
        assert result["external_writes_enabled"] is False
        assert result["product_fields_saved"] == 0
        assert db.scalars(select(EcommApiProductEdit)).all() == []
        assert db.scalars(select(KikiAiEditorialDraft)).all() == []
        current = db.get(Dossier, IDENT)
        assert len(current.facts) == 3
        assert all(f["state"] == "PENDING" for f in current.facts)
        previous_versions = [(f["id"], f["version"]) for f in current.facts]
        again = extract_reviewed_selection(db, user, [IDENT])
        assert again["counts"]["NO_CHANGES"] == 0 or again["counts"]["NO_CHANGES"] == 1
        assert [(f["id"], f["version"]) for f in db.get(Dossier, IDENT).facts] == previous_versions


def test_already_approved_facts_remain_approved_and_unchanged(tmp_path, monkeypatch):
    engine = setup(tmp_path, monkeypatch)
    user = SimpleNamespace(id=1)
    with Session(engine) as db:
        svc, imported, doc_id = attach_reviewed_real_original(db, user)
        doc = svc.research._document(doc_id)
        svc.research.review_document_identity(
            IDENT, imported["version"], doc_id, doc.version, "APPROVED",
            "Revisé las citas exactas del HTML de prueba para esta variante.",
        )
        first = extract_reviewed_selection(db, user, [IDENT])
        assert first["items"][0]["facts_pending"] == 3
        dossier = db.get(Dossier, IDENT)
        candidate = dossier.facts[0]
        svc.research.review(
            IDENT, dossier.version, candidate["id"], candidate["version"],
            "APPROVED", "Comprobé el fragmento literal en el archivo ficticio.",
        )
        old = db.get(Dossier, IDENT)
        before = [(f["id"], f["version"], f["state"]) for f in old.facts]
        after = extract_reviewed_selection(db, user, [IDENT])
        assert after["items"][0]["facts_approved_unchanged"] == 1
        assert after["items"][0]["facts_pending"] == 2
        assert [(f["id"], f["version"], f["state"]) for f in db.get(Dossier, IDENT).facts] == before


@pytest.mark.parametrize("ids", [
    [], [IDENT, IDENT], ["bad-id"], ["-2"], [str(i) for i in range(1, 22)],
    [IDENT, "9999999999999"],
])
def test_selection_fails_closed_without_provider_calls(tmp_path, monkeypatch, ids):
    engine = setup(tmp_path, monkeypatch)
    with Session(engine) as db:
        with pytest.raises(ValueError):
            extract_reviewed_selection(db, SimpleNamespace(id=1), ids)
        assert db.scalars(select(EcommApiProductEdit)).all() == []
