"""No-provider, SQLite regression: documentary sources -> editor suggestions.

Never makes a network request or touches Render / Ecomm / Mercado Libre.
"""
from copy import deepcopy
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.services.documental.research import Research
from app.services.documental.source_links import suggest_reviewed_sources
from app.services.documental.storage import Document
from test_documental_complete_draft_flow import IDENT, DOCUMENT_ID, prepare


def test_human_review_required_and_never_automatically_verifies(tmp_path, monkeypatch):
    import app.services.documental.research as module
    monkeypatch.setattr(
        module, "get_settings", lambda: SimpleNamespace(kiki_admin_username="test"),
    )
    engine, _capture = prepare(tmp_path)
    with Session(engine) as db:
        doc = db.get(Document, DOCUMENT_ID)
        body = deepcopy(doc.body)
        body["synthetic"] = False
        # Test fixture uses .invalid, which is a never-resolved reserved TLD.
        # A direct reference is metadata only; the helper performs NO fetch.
        body["source"] = {
            "review_state": "PENDING",
            "reference_url": "https://fabricante-prueba.invalid/mix-250g",
            "capture_mode": "USER_SAVED_WEB_HTML",
        }
        body["original"] = {"sha256": "a" * 64, "size": 180}
        body["parse_status"] = "TEXT_EXTRACTED"
        doc.body = body
        db.commit()

    with Session(engine) as db:
        research = Research(db, SimpleNamespace(id=1))
        assert suggest_reviewed_sources(research, IDENT)["suggestions"] == []

        doc = db.get(Document, DOCUMENT_ID)
        doc.body = {**doc.body, "source": {**doc.body["source"], "review_state": "REVIEWED"}}
        db.flush()
        assert suggest_reviewed_sources(research, IDENT)["suggestions"] == []

        dossier = research.dossier(IDENT)
        review = research.review_document_identity(
            IDENT, dossier.version, DOCUMENT_ID, 1, "APPROVED",
            "Revisé identidad del archivo de prueba y su presentación de 250 g.",
        )
        assert suggest_reviewed_sources(research, IDENT)["suggestions"] == []

        extracted = research.extract(IDENT, review["version"], DOCUMENT_ID, 1)
        assert len(extracted["facts"]) == 3
        assert suggest_reviewed_sources(research, IDENT)["suggestions"] == []

        fact = extracted["facts"][0]
        research.review(
            IDENT, extracted["version"], fact["id"], fact["version"], "APPROVED",
            "Comprobé exactamente el nombre ficticio y su cita original.",
        )
        response = suggest_reviewed_sources(research, IDENT)
        assert response["ecomm_id"] == IDENT
        assert response["internal_only"] is True
        assert response["external_writes_enabled"] is False
        assert response["automatically_verified"] is False
        assert len(response["suggestions"]) == 1
        candidate = response["suggestions"][0]
        assert candidate["source"]["kind"] == "OTRO"
        assert candidate["source"]["verified"] is False
        assert candidate["source"]["url"] == "https://fabricante-prueba.invalid/mix-250g"
        assert candidate["document_id"] == DOCUMENT_ID
        assert candidate["sha256"] == "a" * 64
        assert candidate["approved_fact_count"] == 1
        assert "EAN" not in str(candidate)
        assert suggest_reviewed_sources(research, IDENT)["suggestions"] == response["suggestions"]


def test_mismatched_identity_url_or_revoked_provenance_cannot_be_reused(tmp_path, monkeypatch):
    import app.services.documental.research as module
    monkeypatch.setattr(
        module, "get_settings", lambda: SimpleNamespace(kiki_admin_username="test"),
    )
    engine, _capture = prepare(tmp_path)
    with Session(engine) as db:
        research = Research(db, SimpleNamespace(id=1))
        item = research.dossier(IDENT)
        doc = db.get(Document, DOCUMENT_ID)
        body = deepcopy(doc.body)
        body["synthetic"] = False
        body["parse_status"] = "TEXT_EXTRACTED"
        body["original"] = {"sha256": "a" * 64, "size": 180}
        body["source"]["reference_url"] = "https://localhost/internal"
        doc.body = body
        db.flush()
        assert suggest_reviewed_sources(research, IDENT)["suggestions"] == []

        body = deepcopy(doc.body)
        body["source"]["reference_url"] = "https://fabricante-prueba.invalid/mix-250g"
        body["associated_ecomm_id"] = "someone-else"
        doc.body = body
        db.flush()
        assert suggest_reviewed_sources(research, IDENT)["suggestions"] == []
        assert item.ecomm_id == IDENT

        body["associated_ecomm_id"] = IDENT
        body["source"]["review_state"] = "REVOKED"
        doc.body = deepcopy(body)
        db.flush()
        assert suggest_reviewed_sources(research, IDENT)["suggestions"] == []
