"""Original-linked commercial media rights approval is a separate human gate.

Every file and grant in this suite is fabricated. These tests verify program
controls, not authorship or legal validity of an actual manufacturer's licence.
"""
import base64
from copy import deepcopy
from hashlib import sha256

import pytest
from sqlalchemy.orm import Session

from app.services.documental.media_rights import (
    latest_media_rights, media_grant_current, original_grant_is_current,
    review_media_rights,
)
from app.services.documental.research import Research
from app.services.documental.storage import Document, digest
from test_documental_channel_readiness_guard import (
    URL, complete_fields, install_fake_source, prepare, setting,
)


def case(tmp_path, monkeypatch):
    from app.core import config
    import app.services.documental.research as research_module

    monkeypatch.setattr(config, "get_settings", lambda: setting())
    monkeypatch.setattr(research_module, "get_settings", lambda: setting())
    engine, _ = prepare(tmp_path)
    return engine


def test_explicit_grant_survives_reopen_but_not_a_different_asset(
    tmp_path, monkeypatch,
):
    engine = case(tmp_path, monkeypatch)
    with Session(engine) as db:
        doc, user = install_fake_source(db)
        service = Research(db, user)
        dossier = service.dossier("7518949")
        media = complete_fields()["media"][0]
        assert media_grant_current(service, dossier, media)
        assert latest_media_rights(
            dossier, "IMAGE", media["url"]
        )["decision"] == "APPROVED"
        changed = {**media, "url": media["url"].replace("imagen.png", "otra.png")}
        assert not media_grant_current(service, dossier, changed)
        changed = {**media, "source_url": "https://otra-fuente.invalid/asset"}
        assert not media_grant_current(service, dossier, changed)
        assert original_grant_is_current(
            doc, media["url"], "texto/linea/6",
            doc.body["sections"]["texto/linea/6"],
        )
    with Session(engine) as db:
        doc, service = db.get(Document, doc.id), Research(db, user)
        assert media_grant_current(
            service, service.dossier("7518949"), media
        )
        assert doc.version == 1


def test_photo_on_a_public_page_is_not_written_permission(
    tmp_path, monkeypatch,
):
    engine = case(tmp_path, monkeypatch)
    with Session(engine) as db:
        doc, user = install_fake_source(db)
        research = Research(db, user)
        dossier = research.dossier("7518949")
        url = complete_fields()["media"][0]["url"]
        page_text = f"<img src='{url}' alt='Producto'>"
        assert not original_grant_is_current(doc, url, "texto/linea/6", page_text)
        with pytest.raises(ValueError, match="No hay permiso explícito"):
            review_media_rights(
                research, "7518949", dossier.version, doc.id, doc.version,
                url, "IMAGE", URL, "APPROVED", "DOCUMENTED_LICENSE",
                "texto/linea/6", page_text,
                "La página pública contiene una foto, pero no una licencia escrita.",
            )


@pytest.mark.parametrize("tamper", [
    "new_doc_digest", "source_rejected", "original_changed",
    "permission_removed", "other_document", "identity_changed",
])
def test_document_or_identity_drift_revokes_effective_media_permission(
    tmp_path, monkeypatch, tamper
):
    engine = case(tmp_path, monkeypatch)
    with Session(engine) as db:
        doc, user = install_fake_source(db)
        media = complete_fields()["media"][0]
        research = Research(db, user)
        dossier = research.dossier("7518949")
        assert media_grant_current(research, dossier, media)
        if tamper == "new_doc_digest":
            doc.digest = "e" * 64
        elif tamper == "source_rejected":
            body = deepcopy(doc.body)
            body["source"]["review_state"] = "REVOKED"
            doc.body = body
        elif tamper == "original_changed":
            body = deepcopy(doc.body)
            body["original_base64"] = "Zm9yZ2Vk"
            doc.body = body
        elif tamper == "permission_removed":
            body = deepcopy(doc.body)
            body["sections"]["texto/linea/6"] = "Solo imagen ilustrativa"
            doc.body = body
        elif tamper == "other_document":
            media["url"] = "https://fabricante-prueba.invalid/imagen-2.png"
        else:
            dossier.identity["sku"] = "SKU-CAMBIO"
            dossier.identity_digest = "f" * 64
        db.flush()
        assert not media_grant_current(research, dossier, media)


def test_explicit_revocation_and_stale_version_cannot_be_bypassed(
    tmp_path, monkeypatch,
):
    engine = case(tmp_path, monkeypatch)
    with Session(engine) as db:
        doc, user = install_fake_source(db)
        research = Research(db, user)
        dossier = research.dossier("7518949")
        fields = complete_fields()
        media = fields["media"][0]
        quote = doc.body["sections"]["texto/linea/6"]
        with pytest.raises(ValueError, match="otra sesión"):
            review_media_rights(
                research, "7518949", 0, doc.id, doc.version,
                media["url"], "IMAGE", URL, "REVOKED", "OWNER_AUTHORIZATION",
                "texto/linea/6", quote,
                "Se revoca expresamente el permiso ficticio para esta imagen.",
            )
        review_media_rights(
            research, "7518949", dossier.version, doc.id, doc.version,
            media["url"], "IMAGE", URL, "REVOKED", "OWNER_AUTHORIZATION",
            "texto/linea/6", quote,
            "Se revoca expresamente el permiso ficticio para esta imagen.",
        )
        refreshed = research.dossier("7518949")
        assert not media_grant_current(research, refreshed, media)
        with pytest.raises(ValueError, match="No existe permiso vigente"):
            review_media_rights(
                research, "7518949", refreshed.version, doc.id, doc.version,
                media["url"], "IMAGE", URL, "REVOKED", "OWNER_AUTHORIZATION",
                "texto/linea/6", quote,
                "Se revoca expresamente el permiso ficticio ya revocado.",
            )



@pytest.mark.parametrize("grant_text,accepted", [
    (
        "El titular NO autoriza el uso comercial de "
        "https://fabricante-prueba.invalid/imagen.png en KIKI.",
        False,
    ),
    (
        "La licencia solo permite el uso privado de "
        "https://fabricante-prueba.invalid/imagen.png.",
        False,
    ),
    (
        "El uso comercial de https://fabricante-prueba.invalid/imagen.png "
        "está prohibido por el titular de derechos.",
        False,
    ),
    (
        "Licencia de uso comercial de "
        "https://fabricante-prueba.invalid/imagen.png "
        "otorgada expresamente por el titular a KIKI.",
        True,
    ),
])
def test_quote_must_explicitly_authorize_commercial_use_without_denial(
    tmp_path, monkeypatch, grant_text, accepted,
):
    engine = case(tmp_path, monkeypatch)
    with Session(engine) as db:
        doc, _user = install_fake_source(db)
        body = deepcopy(doc.body)
        body["sections"]["texto/linea/6"] = grant_text
        raw = "\n".join(body["sections"].values()).encode("utf-8")
        checksum = sha256(raw).hexdigest()
        body["original_base64"] = base64.b64encode(raw).decode("ascii")
        body["original"]["size"] = len(raw)
        body["original"]["sha256"] = checksum
        body["provenance"] = "local://sha256/" + checksum
        doc.body = body
        doc.digest = digest(body)
        db.flush()
        assert original_grant_is_current(
            doc, "https://fabricante-prueba.invalid/imagen.png",
            "texto/linea/6", grant_text,
        ) is accepted
