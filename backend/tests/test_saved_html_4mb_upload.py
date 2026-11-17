"""Saved manufacturer HTML with large inert scripts: no external calls, no auto approval.

The test original is synthetic. It is NOT the Geonat page: Geonat's
authentic original can only be checked when the user uploads it in KIKI.
"""
import base64
import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.services.documental.contracts import Incorporate
from app.services.documental.local_documents import LocalDocuments
from app.services.documental.storage import Document
from document_reader.parser import MAX_SAVED_HTML_BYTES, parse
from test_documental_complete_draft_flow import IDENT, prepare
from test_documental_saved_page_html import saved_page


REAL_USER_FILE_BYTES = 4_034_560
URL = "https://fabricante-prueba.invalid/producto/ejemplo"


def original_html(size=REAL_USER_FILE_BYTES):
    anchor = saved_page(extra_html="<script></script>")
    extra = size - len(anchor.encode("utf-8"))
    assert extra >= 0
    original = saved_page(extra_html="<script>" + "z" * extra + "</script>").encode("utf-8")
    assert len(original) == size
    return original


def valid_input(original, *, snapshot=True, filename="fabricante.html", content_type="text/html"):
    return dict(
        kind="FILE",
        web_snapshot=snapshot,
        expected_version=0,
        filename=filename,
        content_type=content_type,
        content_base64=base64.b64encode(original).decode("ascii"),
        provenance_note="Página web oficial guardada como HTML; operador debe comprobar identidad.",
        reference_url=URL,
        declared_official=True,
        declared_consulted_at=datetime(2026, 11, 17, tzinfo=timezone.utc),
        authorized_local_processing=True,
    )


def test_html_of_exact_user_size_keeps_evidence_bounded_and_original_bytes(tmp_path, monkeypatch):
    import app.services.documental.research as research_module
    monkeypatch.setattr(
        research_module, "get_settings",
        lambda: SimpleNamespace(kiki_admin_username="test"),
    )
    raw = original_html()
    request = Incorporate(**valid_input(raw))
    assert len(raw) < MAX_SAVED_HTML_BYTES
    parsed = parse(
        request.filename, request.content_type, request.content_base64,
        web_snapshot=request.web_snapshot,
    )
    assert parsed["identity"]["name"] == "Mix Ensaladas y Sopas"
    assert parsed["identity"]["presentation"] == "250 g"
    assert parsed["identity"]["ean"] is None
    assert parsed["parse_status"] == "TEXT_EXTRACTED"
    assert "zzzz" not in repr(parsed)
    assert not parsed["claims"] or all(not x.get("verified") for x in parsed["claims"])
    # The framed UNIX-socket request remains below the parser's already
    # established pinned-PDF transport size. No transport increase needed.
    from document_reader.hileret_brochure import MAX_REQUEST
    packet = json.dumps({
        "filename": request.filename,
        "content_type": request.content_type,
        "content_base64": request.content_base64,
        "web_snapshot": True,
    }).encode()
    assert len(packet) < MAX_REQUEST

    engine, _ = prepare(tmp_path)
    with Session(engine) as db:
        imported = LocalDocuments(db, SimpleNamespace(id=1)).incorporate(
            IDENT, request, parsed,
        )
        doc = db.get(Document, imported["incorporated_document_id"])
        assert doc.body["source"]["capture_mode"] == "USER_SAVED_WEB_HTML"
        assert doc.body["source"]["review_state"] == "PENDING"
        assert doc.body["original"]["sha256"] == hashlib.sha256(raw).hexdigest()
        assert doc.body["original"]["size"] == REAL_USER_FILE_BYTES
        assert base64.b64decode(doc.body["original_base64"]) == raw
        assert imported["facts"] == []


def test_only_web_snapshot_html_can_exceed_512kib():
    oversized = original_html(524_289)
    valid = Incorporate(**valid_input(oversized))
    assert valid.web_snapshot
    with pytest.raises(ValidationError):
        Incorporate(**valid_input(oversized, snapshot=False))
    with pytest.raises(ValidationError):
        Incorporate(**valid_input(oversized, filename="fabricante.pdf", content_type="application/pdf"))
    with pytest.raises(ValidationError):
        Incorporate(**valid_input(oversized, filename="fabricante.txt", content_type="text/plain"))


def test_maximum_saved_html_is_strict_and_scripts_never_become_evidence():
    raw = original_html(MAX_SAVED_HTML_BYTES)
    validated = Incorporate(**valid_input(raw))
    assert validated.web_snapshot is True
    parsed = parse(validated.filename, validated.content_type, validated.content_base64, web_snapshot=True)
    assert parsed["identity"]["ean"] is None
    assert parsed["identity"]["name"] == "Mix Ensaladas y Sopas"
    with pytest.raises(ValidationError, match="4 MiB"):
        Incorporate(**valid_input(raw + b"x"))
