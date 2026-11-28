"""Media rights: fictional licences in disposable DBs, never provider traffic."""
import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import EcommApiProductEdit
from app.services.documental.media_rights import (
    media_grant_current, media_permission_report, media_review_registry,
    original_grant_is_current, review_media_rights, safe_media_url,
)
from app.services.documental.research import Research
from app.services.documental.storage import Document, digest
from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
from test_documental_channel_readiness_guard import (
    IDENT, URL, complete_fields, install_fake_source,
)
from test_documental_media_rights import case


def stored_edit(db):
    return db.scalar(select(EcommApiProductEdit).where(EcommApiProductEdit.ecomm_id == IDENT))


def bound_case(tmp_path, monkeypatch):
    engine = case(tmp_path, monkeypatch)
    with Session(engine) as db:
        doc, user = install_fake_source(db)
        fields = complete_fields()
        edit = EcommApiProductWorkspace(db).save(IDENT, fields, "DRAFT", 0)
        research = Research(db, user)
        item = research.dossier(IDENT)
        media = fields["media"][0]
        result = review_media_rights(
            research, IDENT, item.version, doc.id, doc.version,
            media["url"], media["kind"], media["source_url"], "APPROVED",
            "OWNER_AUTHORIZATION", "texto/linea/6", doc.body["sections"]["texto/linea/6"],
            "Revisé el permiso ficticio para esta imagen, presentación y texto alternativo exactos.",
            alt_text=media["alt"], presentation=fields["presentation"],
            expected_workspace_version=edit["version"], valid_until="2030-12-31T23:59:00+00:00",
        )
        db.commit()
        assert result["media_rights"][0]["stage4_ready"] is True
    return engine, user, media


def test_registry_recovers_exact_saved_resource_and_permission_receipt(tmp_path, monkeypatch):
    engine, user, media = bound_case(tmp_path, monkeypatch)
    with Session(engine) as db:
        research = Research(db, user)
        edit = stored_edit(db)
        before = deepcopy(edit.fields), edit.version
        report = media_review_registry(research, IDENT, edit.fields)
        assert report["ecomm_id"] == IDENT
        assert report["remote_resources_loaded"] == 0
        assert report["external_writes_enabled"] is False
        asset = report["entries"][0]
        assert asset["state"] == "APPROVED_CURRENT"
        assert asset["stage4_ready"] is asset["metadata_complete"] is asset["preview_allowed"] is True
        assert asset["alt"] == asset["reviewed_alt"] == media["alt"]
        assert asset["presentation"] == complete_fields()["presentation"]
        assert len(asset["original_sha256"]) == 64
        assert asset["reviewed_at"] and asset["valid_until"]
        assert not asset["blockers"]
        assert all("original_base64" not in doc for doc in report["documents"])
        assert (edit.fields, edit.version) == before


@pytest.mark.parametrize("change", ["alt", "source", "presentation", "expiry", "doc-digest"])
def test_changed_asset_or_document_cannot_reuse_permission(tmp_path, monkeypatch, change):
    engine, user, media = bound_case(tmp_path, monkeypatch)
    with Session(engine) as db:
        research = Research(db, user)
        item = research.dossier(IDENT)
        edit = stored_edit(db)
        fields = deepcopy(edit.fields)
        if change == "alt":
            fields["media"][0]["alt"] = "Otra descripción alternativa no revisada"
        elif change == "source":
            fields["media"][0]["source_url"] = "https://otra-fuente.invalid/permiso"
        elif change == "presentation":
            fields["presentation"] = "500 g"
        elif change == "expiry":
            history = deepcopy(item.history)
            history[-1]["detail"]["valid_until"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            item.history = history
        else:
            db.get(Document, "local-" + "a" * 32).digest = "f" * 64
        edit.fields = fields
        db.flush()
        report = media_permission_report(research, item, fields["media"])[0]
        assert report["current"] is report["stage4_ready"] is report["preview_allowed"] is False
        assert report["blockers"]


def test_legacy_permission_remains_explicitly_incomplete_for_stage4(tmp_path, monkeypatch):
    engine = case(tmp_path, monkeypatch)
    with Session(engine) as db:
        _doc, user = install_fake_source(db)
        media = complete_fields()["media"][0]
        service = Research(db, user)
        report = media_permission_report(service, service.dossier(IDENT), [media])[0]
        assert report["current"] is True
        assert report["metadata_complete"] is report["stage4_ready"] is report["preview_allowed"] is False
        assert report["blockers"]


@pytest.mark.parametrize("decision", ["REJECTED", "REVOKED"])
def test_negative_decision_is_persisted_without_changing_editor(tmp_path, monkeypatch, decision):
    engine, user, media = bound_case(tmp_path, monkeypatch)
    with Session(engine) as db:
        research = Research(db, user)
        item = research.dossier(IDENT)
        doc = research._document("local-" + "a" * 32)
        edit = stored_edit(db)
        original = deepcopy(edit.fields), edit.version
        result = review_media_rights(
            research, IDENT, item.version, doc.id, doc.version,
            media["url"], "IMAGE", URL, decision, "OWNER_AUTHORIZATION",
            "texto/linea/6", doc.body["sections"]["texto/linea/6"],
            "Decisión humana ficticia: este recurso no debe utilizarse comercialmente.",
            alt_text=media["alt"], presentation=edit.fields["presentation"],
            expected_workspace_version=edit.version,
        )
        assert result["media_rights"][0]["state"] == decision
        assert result["media_rights"][0]["stage4_ready"] is False
        assert (edit.fields, edit.version) == original
        db.commit()
    with Session(engine) as db:
        item = Research(db, user).dossier(IDENT)
        assert item.history[-1]["detail"]["decision"] == decision


def test_workspace_conflict_and_wrong_presentation_are_rejected(tmp_path, monkeypatch):
    engine, user, media = bound_case(tmp_path, monkeypatch)
    with Session(engine) as db:
        research = Research(db, user)
        item = research.dossier(IDENT)
        doc = research._document("local-" + "a" * 32)
        args = (research, IDENT, item.version, doc.id, doc.version, media["url"], "IMAGE", URL, "APPROVED", "OWNER_AUTHORIZATION", "texto/linea/6", doc.body["sections"]["texto/linea/6"], "Revisión ficticia con conflicto de versión o presentación que debe bloquearse.")
        with pytest.raises(ValueError, match="otra sesión"):
            review_media_rights(*args, alt_text=media["alt"], presentation="250 g", expected_workspace_version=0)
        with pytest.raises(ValueError, match="presentación"):
            review_media_rights(*args, alt_text=media["alt"], presentation="500 g", expected_workspace_version=stored_edit(db).version)


def test_bound_receipt_supports_metadata_projection_without_parsing(tmp_path, monkeypatch):
    engine, user, media = bound_case(tmp_path, monkeypatch)
    with Session(engine) as db:
        research = Research(db, user)
        item = research.dossier(IDENT)
        original = research._document("local-" + "a" * 32)
        body = deepcopy(original.body)
        del body["original_base64"]
        projection = SimpleNamespace(id=original.id, version=original.version, digest=original.digest, body=body)
        monkeypatch.setattr(research, "_document", lambda ident: projection)
        assert media_grant_current(research, item, media)
        projection.digest = "0" * 64
        assert not media_grant_current(research, item, media)


@pytest.mark.parametrize("url", ["http://public.example/a", "https://localhost/a", "https://127.0.0.1/a", "https://0177.0.0.1/a", "https://0x7f.0.0.1/a", "https://10.0.0.1/a", "https://[::1]/a", "https://user:secret@example.com/a", "https://example.com:444/a", "https://example.internal/a", "javascript:alert(1)"])
def test_preview_reference_rejects_obvious_private_or_credential_urls(url):
    assert not safe_media_url(url)


def pdf_bytes(text):
    """A small compressed PDF constructed locally, not customer evidence."""
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=1000, height=150)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    lines = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in text.splitlines()]
    stream.set_data(("BT /F1 8 Tf 10 100 Td " + " 0 -14 Td ".join("(" + line + ") Tj" for line in lines) + " ET").encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream.flate_encode())
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def document_from_bytes(raw, quote, location, sections):
    checksum = sha256(raw).hexdigest()
    body = {"version": 1, "synthetic": False, "origin_kind": "FILE", "parse_status": "TEXT_EXTRACTED", "parser_blockers": [], "original": {"filename": "permiso.pdf", "content_type": "application/pdf", "sha256": checksum, "size": len(raw)}, "provenance": "local://sha256/" + checksum, "original_base64": base64.b64encode(raw).decode(), "sections": sections, "source": {"review_state": "REVIEWED", "reviewer": "Operador ficticio del ensayo", "review_reason": "Revisé expresamente el documento de prueba."}}
    return SimpleNamespace(id="local-" + "b" * 32, version=1, body=body, digest=digest(body))


def actual_parser(body):
    from document_reader.parser import parse
    return parse(body.filename, body.content_type, body.content_base64, web_snapshot=body.web_snapshot)


def test_compressed_pdf_permission_is_verified_from_bounded_parser_not_raw_utf8():
    from document_reader.parser import parse
    url = "https://fabricante-prueba.invalid/imagen.png"
    quote = f"El titular autoriza el uso comercial de {url} en KIKI."
    raw = pdf_bytes("Nombre: Producto ficticio de prueba\nPresentacion: 250 g\n" + quote)
    assert quote.encode() not in raw
    parsed = parse("permiso.pdf", "application/pdf", base64.b64encode(raw).decode())
    location = next(key for key, value in parsed["sections"].items() if quote in value)
    doc = document_from_bytes(raw, quote, location, parsed["sections"])
    assert original_grant_is_current(doc, url, location, quote, parser=actual_parser)
    doc.body["sections"][location] = quote + " inventado"
    doc.digest = digest(doc.body)
    assert not original_grant_is_current(doc, url, location, quote + " inventado", parser=actual_parser)


def test_authentic_hileret_pdf_does_not_become_a_media_licence():
    candidate = Path("/pilot-inputs/hileret-original.pdf")
    if not candidate.is_file():
        candidate = Path(__file__).resolve().parents[2] / "integration/fixtures/hileret-original.pdf"
    if not candidate.is_file():
        pytest.skip("PDF original Hileret no disponible localmente; no se descarga.")
    raw = candidate.read_bytes()
    assert sha256(raw).hexdigest() == "bd99c29548cbf683e57b1fd6f2973f37ccef76477e2f6bc45379017a63599291"
    url = "https://fabricante-prueba.invalid/foto.png"
    invented = f"El titular autoriza el uso comercial de {url} en KIKI."
    location = "pagina/2/permiso-inexistente"
    doc = document_from_bytes(raw, invented, location, {location: invented})
    assert not original_grant_is_current(doc, url, location, invented, parser=actual_parser)
