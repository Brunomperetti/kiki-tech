"""Offline original HTML -> archival -> human review -> source-backed draft.

Representative HTML is a *fictional test fixture* (not copied from or
authenticated by the manufacturer's live site). This touches only SQLite.
"""
import base64
from datetime import datetime, timezone
import hashlib
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.services.documental.contracts import Incorporate, Provenance, BatchFactApproval, BatchFactReview
from app.services.documental.local_documents import LocalDocuments, parse_local
from app.services.documental.research import Research
from app.services.documental.proposals import Proposals
from app.services.documental.storage import Document
from document_reader.parser import parse
from test_documental_complete_draft_flow import IDENT, prepare
from test_documental_saved_page_html import saved_page


URL = "https://naturalseed.com.ar/producto/mix-ensaladas-y-sopas/"


def upload_payload(*, version=0, web=True, kind="FILE", url=URL, consulted=True):
    original = saved_page().encode("utf-8")
    return Incorporate(
        kind=kind,
        expected_version=version,
        filename="natural-seed-pagina-guardada.html" if kind == "FILE" else "",
        content_type="text/html" if kind == "FILE" else "",
        content_base64=base64.b64encode(original).decode() if kind == "FILE" else "",
        web_snapshot=web,
        provenance_note="Archivo HTML guardado por un operador; autenticidad todavía no confirmada.",
        reference_url=url,
        declared_official=True,
        declared_manufacturer="Natural Seed",
        declared_consulted_at=datetime(2026, 11, 15, tzinfo=timezone.utc) if consulted else None,
        authorized_local_processing=True,
    )


def test_operator_saved_page_is_archived_before_any_identity_or_fact_approval(
    tmp_path, monkeypatch
):
    import app.services.documental.research as research_module

    monkeypatch.setattr(
        research_module, "get_settings",
        lambda: SimpleNamespace(kiki_admin_username="test"),
    )
    engine, original_capture = prepare(tmp_path)
    original = saved_page().encode("utf-8")
    payload = upload_payload()

    # Real isolated UDS is not available in pytest: feed the exact validated
    # parser result into the genuine LocalDocuments service for this regression.
    parsed = parse(
        payload.filename, payload.content_type, payload.content_base64,
        web_snapshot=payload.web_snapshot,
    )
    user = SimpleNamespace(id=1)
    with Session(engine) as db:
        service = LocalDocuments(db, user)
        imported = service.incorporate(IDENT, payload, parsed)
        doc_id = imported["incorporated_document_id"]
        doc = db.get(Document, doc_id)
        assert doc.body["source"]["capture_mode"] == "USER_SAVED_WEB_HTML"
        assert doc.body["source"]["review_state"] == "PENDING"
        assert doc.body["source"]["reference_url"] == URL
        assert doc.body["source"]["declared_official"] is True
        assert doc.body["original"]["sha256"] == hashlib.sha256(original).hexdigest()
        assert doc.body["original"]["size"] == len(original)
        assert doc.body["identity"]["name"] == "Mix Ensaladas y Sopas"
        assert doc.body["identity"]["presentation"] == "250 g"
        assert not imported["facts"]  # no verified facts from raw text

        restored = service.original(IDENT, doc_id, 1)
        assert base64.b64decode(restored["content_base64"]) == original
        assert restored["external_writes_enabled"] is False

        # A checked "official" box is only a declaration, not source review.
        with pytest.raises(ValueError, match="procedencia documental revisada"):
            service.research.review_document_identity(
                IDENT, imported["version"], doc_id, 1, "APPROVED",
                "Revisé el nombre exacto y el peso de la etiqueta original.",
            )

        current = service.provenance(
            IDENT, doc_id, Provenance(
                expected_document_version=1,
                decision="REVIEWED",
                reason="Comprobé manualmente la página y el origen del archivo ficticio.",
            ),
        )
        latest_doc = db.get(Document, doc_id)
        assert latest_doc.version == 2
        assert latest_doc.digest != doc.digest or latest_doc.version != 1

        reviewed = service.research.review_document_identity(
            IDENT, current["version"], doc_id, latest_doc.version, "APPROVED",
            "Contrasté el nombre y el peso del HTML ficticio con esta variante.",
        )
        assert reviewed["documents"]
        extraction = service.research.extract(
            IDENT, reviewed["version"], doc_id, latest_doc.version,
        )
        assert len([fact for fact in extraction["facts"] if fact["document_id"] == doc_id]) == 3
        assert all(not f["verified"] for f in extraction["facts"])
        # A proposal from unapproved facts is empty: human approval is mandatory.
        assert Proposals(db, user).latest(IDENT)["authorized_facts"] == []

        # Batch review must reject one stale fact without approving any others.
        live_case = service.research.dossier(IDENT)
        batch = [
            BatchFactApproval(
                fact_id=fact["id"],
                expected_fact_version=fact["version"],
                reason=f"Revisé el fragmento individual del campo {fact['field']}.",
            )
            for fact in extraction["facts"]
        ]
        with pytest.raises(ValueError, match="cambió de versión"):
            service.research.review_batch(
                IDENT, live_case.version, doc_id, latest_doc.version,
                [batch[0], batch[1].model_copy(update={"expected_fact_version": 999})],
            )
        assert all(f["state"] == "PENDING" for f in live_case.facts)
        # Human selection of each claim + current versions: one persisted decision.
        request = BatchFactReview(
            expected_version=live_case.version,
            document_id=doc_id,
            document_version=latest_doc.version,
            confirm=True,
            facts=batch,
        )
        extraction = service.research.review_batch(
            IDENT, request.expected_version, request.document_id,
            request.document_version, request.facts,
        )
        assert extraction["history"][-1]["action"] == "REVIEW_BATCH"
        assert all(f["verified"] for f in extraction["facts"])
        with pytest.raises(ValueError, match="ya fue decidido"):
            service.research.review_batch(
                IDENT, extraction["version"], doc_id, latest_doc.version, batch,
            )
        assert all(f["verified"] for f in service.research.dossier(IDENT).facts)
        # Reconfirming a source already reviewed must preserve the immutable
        # source version/hash and the operator-approved evidence.
        dossier_before = service.research.dossier(IDENT)
        dossier_version_before = dossier_before.version
        original_version = latest_doc.version
        original_digest = latest_doc.digest
        original_history_length = len(latest_doc.history)
        reaffirmed = service.provenance(
            IDENT, doc_id, Provenance(
                expected_document_version=original_version,
                decision="REVIEWED",
                reason="Volví a cotejar el original archivado sin cambiar sus datos.",
            ),
        )
        assert latest_doc.version == original_version
        assert latest_doc.digest == original_digest
        assert len(latest_doc.history) == original_history_length
        assert reaffirmed["version"] == dossier_version_before + 1
        assert reaffirmed["history"][-1]["action"] == "PROVENANCE_RECONFIRMED"
        assert reaffirmed["history"][-1]["detail"]["document_hash"] == original_digest
        assert all(f["verified"] for f in reaffirmed["facts"])
        assert service.research.equivalence_current(
            service.research.dossier(IDENT), latest_doc
        )
        draft = Proposals(db, user).generate(IDENT, 0)
        assert draft["fields"]["title"]["value"] == "Mix Ensaladas y Sopas · 250 g"
        assert draft["fields"]["short_title"]["value"] == "Mix Ensaladas y Sopas"
        assert draft["fields"]["seo_keywords"]["value"] == "Mix Ensaladas y Sopas, 250 g"
        assert "description" in draft["fields"]
        assert "3 frutos secos + 3 semillas al oreganato" in draft["fields"]["description"]["value"]
        assert "Características" in draft["fields"]["description"]["value"]
        assert any(
            row["name"] == "Características verificables"
            and row["value"] == "3 frutos secos + 3 semillas al oreganato"
            for row in draft["fields"]["attributes"]["value"]
        )
        assert len(draft["fields"]["description"]["evidence_ids"]) == 3
        assert "ingredientes" not in draft["fields"]["description"]["value"].casefold()
        assert "vitamina" not in draft["fields"]["description"]["value"].casefold()
        assert "category" not in draft["fields"]
        assert "media" not in draft["fields"]
        assert not draft["saved_to_product_fields"]

    with Session(engine) as db:
        recovered = db.get(Document, doc_id)
        assert base64.b64decode(recovered.body["original_base64"]) == original
        assert recovered.body["source"]["review_state"] == "REVIEWED"
        assert recovered.version == 2
        assert len(recovered.history) == 1
        assert recovered.history[0]["body"]["source"]["review_state"] == "PENDING"
        research = Research(db, user)
        assert research.equivalence_current(research.dossier(IDENT), recovered)
        from app.database.models import CatalogSnapshot
        from sqlalchemy import select
        assert db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        )).payload == original_capture


def test_saved_web_capture_requires_url_date_and_true_html_format(tmp_path, monkeypatch):
    import app.services.documental.research as research_module

    monkeypatch.setattr(research_module, "get_settings",
                        lambda: SimpleNamespace(kiki_admin_username="test"))
    engine, _ = prepare(tmp_path)
    with Session(engine) as db:
        svc = LocalDocuments(db, SimpleNamespace(id=1))
        source = parse("natural-seed-pagina-guardada.html", "text/html",
                       upload_payload().content_base64, web_snapshot=True)
        with pytest.raises(ValueError, match="HTML original, URL HTTPS y fecha"):
            svc.incorporate(IDENT, upload_payload(url=""), source)
        with pytest.raises(ValueError, match="HTML original, URL HTTPS y fecha"):
            svc.incorporate(IDENT, upload_payload(consulted=False), source)
        with pytest.raises(ValueError, match="captura web debe ser un archivo HTML"):
            parse_local(upload_payload(kind="URL"))
        assert len(svc.research.documents(IDENT)) == 1  # only preexisting test doc
