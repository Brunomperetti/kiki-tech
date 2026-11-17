"""Source-backed channel readiness is strict and OFF by default.

Tests use a disposable SQLite fixture and fictitious original bytes; they
never represent an approved customer product or access any real manufacturer.
"""
import base64
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import CatalogSnapshot, EcommApiProductEdit
from app.services.documental.research import Research
from app.services.documental.storage import Document, digest
from app.services.ecomm_api_product_workspace_service import (
    EcommApiProductWorkspace, blank_fields,
)
from test_documental_complete_draft_flow import (
    IDENT, prepare, synthetic_document, evidence,
)


URL = "https://fabricante-prueba.invalid/mix-250g"


def complete_fields():
    fields = blank_fields()
    fields.update({
        "brand": "Natural Seed",
        "manufacturer": "Natural Seed",
        "title": "Mix Ensaladas y Sopas · 250 g",
        "short_title": "Mix Ensaladas y Sopas",
        "short_description": "Mix Ensaladas y Sopas · 250 g.",
        "description": (
            "Mix Ensaladas y Sopas · 250 g.\n"
            "Características verificables: 3 frutos secos y 3 semillas al oreganato."
        ),
        "details": "Características verificables: 3 frutos secos y 3 semillas al oreganato.",
        "presentation": "250 g",
        "category": "Categoría de prueba",
        "subcategory": "Subcategoría de prueba",
        "seo_title": "Mix Ensaladas y Sopas · 250 g",
        "seo_description": "Mix Ensaladas y Sopas · 250 g.",
        "seo_keywords": (
            "Natural Seed, Mix Ensaladas y Sopas, 250 g, "
            "Categoría de prueba, Subcategoría de prueba"
        ),
        "attributes": [{
            "name": "Características verificables",
            "value": "3 frutos secos y 3 semillas al oreganato",
        }],
        "media": [{
            "kind": "IMAGE",
            "url": "https://fabricante-prueba.invalid/imagen.png",
            "alt": "Imagen ficticia",
            "source_url": URL,
        }],
        "sources": [{
            "kind": "FABRICANTE",
            "name": "Fabricante de prueba",
            "url": URL,
            "note": "Revisé nombre, presentación e identidad del documento.",
            "verified": True,
        }],
    })
    return fields


def setting(enabled=True, pilot=IDENT, workspace=True):
    return SimpleNamespace(
        kiki_document_channel_guard_enabled=enabled,
        kiki_document_channel_guard_pilot_id=pilot,
        kiki_document_workspace_enabled=workspace,
        kiki_admin_username="test",
    )


def install_fake_source(db):
    """Create an actual-shaped *fictitious* local original and approve three facts."""
    doc = db.get(Document, "local-" + "a" * 32)
    body = deepcopy(synthetic_document())
    # Category and subcategory are explicitly quoted and independently
    # reviewed in this synthetic source; commercial editor typing alone fails.
    for field, value, line in (
        ("category", "Categoría de prueba", "4"),
        ("subcategory", "Subcategoría de prueba", "5"),
        ("brand", "Natural Seed", "7"),
        ("manufacturer", "Natural Seed", "8"),
    ):
        location = "texto/linea/" + line
        claim = evidence(field, value, location)
        body["claims"].append(claim)
        body["sections"][location] = claim["quote"]
    # The media permission is entirely fictional but explicit and bound to
    # this image URL; a public product page alone is NOT a licence.
    media_grant = (
        "Licencia: El titular autoriza el uso comercial de "
        "https://fabricante-prueba.invalid/imagen.png en catálogo KIKI."
    )
    body["sections"]["texto/linea/6"] = media_grant
    # Keep the fictional original bytes consistent with its own quoted lines.
    # This still is NOT a manufacturer file or an actual source approval.
    raw = "\n".join(body["sections"].values()).encode("utf-8")
    checksum = sha256(raw).hexdigest()
    body.update({
        "synthetic": False,
        "origin_kind": "FILE",
        "version": 1,
        "provenance": "local://sha256/" + checksum,
        "original": {
            "content_type": "text/plain",
            "filename": "solo-prueba.txt",
            "size": len(raw),
            "sha256": checksum,
        },
        "original_base64": base64.b64encode(raw).decode("ascii"),
    })
    body["source"].update({
        "reference_url": URL,
        "review_state": "REVIEWED",
        "reviewer": "Operador sintético",
        "review_reason": "Contrasté el original sintético de prueba.",
        "reviewed_at": "2026-11-15T09:00:00+00:00",
    })
    body["identity"]["brand"] = "Natural Seed"
    body["identity"]["manufacturer"] = "Natural Seed"
    doc.body = body
    doc.digest = digest(body)
    db.flush()

    user = SimpleNamespace(id=1)
    research = Research(db, user)
    current = research.dossier(IDENT)
    reviewed = research.review_document_identity(
        IDENT, current.version, doc.id, doc.version, "APPROVED",
        "Comparé el nombre y presentación contra el archivo original ficticio.",
    )
    result = research.extract(IDENT, reviewed["version"], doc.id, doc.version)
    for candidate in result["facts"]:
        current = research.dossier(IDENT)
        fact = next(x for x in current.facts if x["id"] == candidate["id"])
        result = research.review(
            IDENT, current.version, fact["id"], fact["version"], "APPROVED",
            "Cita documental de prueba verificada en archivo original ficticio.",
        )
    # Permission requires its own human-reviewed decision, separate from
    # source authenticity and each approved commercial fact.
    from app.services.documental.media_rights import review_media_rights
    item = research.dossier(IDENT)
    review_media_rights(
        research, IDENT, item.version, doc.id, doc.version,
        "https://fabricante-prueba.invalid/imagen.png", "IMAGE", URL,
        "APPROVED", "OWNER_AUTHORIZATION",
        "texto/linea/6", media_grant,
        "Licencia sintética contrastada explícitamente por el operador de prueba.",
    )
    return doc, user


def test_flag_off_preserves_current_legacy_editor_behavior(tmp_path, monkeypatch):
    from app.core import config
    monkeypatch.setattr(config, "get_settings", lambda: setting(enabled=False))
    engine, _ = prepare(tmp_path)
    with Session(engine) as db:
        fields = complete_fields()
        result = EcommApiProductWorkspace(db).save(
            IDENT, fields, "READY_FOR_CHANNELS", 0
        )
        assert result["status"] == "READY_FOR_CHANNELS"
        assert result["version"] == 1
        assert result["readiness"]["ready"] is True


def test_guard_blocks_manual_verified_checkbox_without_archived_source(
    tmp_path, monkeypatch,
):
    from app.core import config
    import app.services.documental.research as research_module

    monkeypatch.setattr(config, "get_settings", lambda: setting())
    monkeypatch.setattr(research_module, "get_settings", lambda: setting())
    engine, _ = prepare(tmp_path)
    with Session(engine) as db:
        editor = EcommApiProductWorkspace(db)
        fields = complete_fields()
        with pytest.raises(ValueError, match="sesión autenticada"):
            editor.save(IDENT, fields, "READY_FOR_CHANNELS", 0)
        with pytest.raises(ValueError, match="Fuente primaria documental"):
            editor.save(IDENT, fields, "READY_FOR_CHANNELS", 0,
                        session=SimpleNamespace(id=1))
        db.rollback()
        assert db.scalars(select(EcommApiProductEdit)).all() == []
        # Drafts remain permitted: the guard must not block legitimate editing.
        saved = editor.save(IDENT, fields, "DRAFT", 0)
        assert saved["status"] == "DRAFT"


@pytest.mark.parametrize("mutation", [
    "removed_original", "tampered_original", "wrong_source_url",
    "pending_source", "unverified_source_checkbox", "wrong_presentation",
    "wrong_short_title", "wrong_sku", "fake_document",
    "unapproved_attribute", "wrong_category", "wrong_subcategory",
    "unapproved_media", "revoked_media_rights",
    "invented_long_description", "invented_short_description",
    "invented_details", "invented_seo_title",
    "invented_seo_description", "invented_seo_keywords",
    "invented_brand", "invented_manufacturer", "unverified_ean",
])
def test_guard_fails_closed_on_absent_or_invalid_source(
    tmp_path, monkeypatch, mutation
):
    from app.core import config
    import app.services.documental.research as research_module

    monkeypatch.setattr(config, "get_settings", lambda: setting())
    monkeypatch.setattr(research_module, "get_settings", lambda: setting())
    engine, _ = prepare(tmp_path)
    with Session(engine) as db:
        doc, user = install_fake_source(db)
        fields = complete_fields()
        if mutation == "removed_original":
            doc.body = {**doc.body, "original_base64": ""}
        elif mutation == "tampered_original":
            doc.body = {**doc.body, "original_base64": base64.b64encode(b"NO").decode()}
        elif mutation == "wrong_source_url":
            fields["sources"][0]["url"] = "https://otra-fuente.invalid/producto"
        elif mutation == "pending_source":
            updated = deepcopy(doc.body)
            updated["source"]["review_state"] = "PENDING"
            doc.body = updated
        elif mutation == "unverified_source_checkbox":
            fields["sources"][0]["verified"] = False
        elif mutation == "wrong_presentation":
            fields["presentation"] = "500 g"
        elif mutation == "wrong_short_title":
            fields["short_title"] = "Otro producto"
        elif mutation == "wrong_category":
            fields["category"] = "Categoría no aprobada"
        elif mutation == "wrong_subcategory":
            fields["subcategory"] = "Otra subcategoría inventada"
        elif mutation == "unapproved_attribute":
            fields["attributes"].append({
                "name": "Sin gluten", "value": "Sí",
            })
        elif mutation == "unverified_ean":
            # An apparently valid barcode from a retailer/Excel is NOT a
            # manufacturer-reviewed individual EAN for the exact SKU.
            fields["proposed_gtin"] = "7798180790097"
        elif mutation.startswith("invented_"):
            key = {
                "invented_long_description": "description",
                "invented_short_description": "short_description",
                "invented_details": "details",
                "invented_seo_title": "seo_title",
                "invented_seo_description": "seo_description",
                "invented_seo_keywords": "seo_keywords",
                "invented_brand": "brand",
                "invented_manufacturer": "manufacturer",
            }[mutation]
            fields[key] += " · Beneficios no aprobados"
        elif mutation == "unapproved_media":
            fields["media"].append({
                "kind": "IMAGE",
                "url": "https://fabricante-prueba.invalid/imagen-2.png",
                "alt": "Sin licencia específica",
                "source_url": URL,
            })
        elif mutation == "revoked_media_rights":
            from app.services.documental.media_rights import review_media_rights
            current = Research(db, user).dossier(IDENT)
            review_media_rights(
                Research(db, user), IDENT, current.version, doc.id, doc.version,
                "https://fabricante-prueba.invalid/imagen.png", "IMAGE",
                URL, "REVOKED", "OWNER_AUTHORIZATION",
                "texto/linea/6", doc.body["sections"]["texto/linea/6"],
                "Revoco la licencia ficticia previamente aprobada para esta imagen.",
            )
        elif mutation == "wrong_sku":
            stage = db.scalar(select(CatalogSnapshot).where(
                CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
            ))
            mutated = deepcopy(stage.payload)
            mutated[0]["items"][0]["variants"][0]["sku"] = "XXX"
            stage.payload = mutated
            db.flush()
        else:
            updated = deepcopy(doc.body)
            updated["synthetic"] = True
            doc.body = updated
        db.flush()
        with pytest.raises(ValueError):
            EcommApiProductWorkspace(db).save(
                IDENT, fields, "READY_FOR_CHANNELS", 0, session=user
            )
        db.rollback()
        assert not db.scalars(select(EcommApiProductEdit)).all()


def test_original_with_approved_identity_allows_guarded_channel_ready(
    tmp_path, monkeypatch
):
    from app.core import config
    import app.services.documental.research as research_module

    monkeypatch.setattr(config, "get_settings", lambda: setting())
    monkeypatch.setattr(research_module, "get_settings", lambda: setting())
    engine, original_capture = prepare(tmp_path)
    with Session(engine) as db:
        _, user = install_fake_source(db)
        editor = EcommApiProductWorkspace(db)
        fields = complete_fields()
        result = editor.save(IDENT, fields, "READY_FOR_CHANNELS", 0, session=user)
        assert result["status"] == "READY_FOR_CHANNELS"
        assert result["readiness"]["ready"] is True
        assert result["external_writes_enabled"] is False
        reread = editor.get(IDENT, session=user)
        assert reread["version"] == 1
        assert reread["documentary_gate"]["enabled"] is True
        assert reread["documentary_gate"]["ready"] is True
        assert reread["readiness"]["ready"] is True
        # Approval of textual facts does NOT grant image copyright.
        from app.services.documental.channel_readiness_guard import require_primary_evidence
        report = require_primary_evidence(db, user, IDENT, fields)
        assert report["commercial_coverage"]["taxonomy_supported"] is True
        assert report["commercial_coverage"]["attributes_supported"] == 1
        assert report["commercial_coverage"]["commercial_copy_supported"] is True
        assert report["commercial_coverage"]["commercial_copy_fields_checked"] == 13
        assert report["commercial_coverage"]["commercial_copy_mismatches"] == []
        assert report["commercial_coverage"]["media_rights_verified"] is True
        assert report["commercial_coverage"]["media_resources_reviewed"] == 1
        current = Research(db, user).dossier(IDENT)
        assert len([fact for fact in current.facts if fact["state"] == "APPROVED"]) == 7
        assert db.get(Document, "local-" + "a" * 32).body["original"]["size"] > 0
        assert db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
        )).payload == original_capture

        # Revocation invalidates new review; no checklist-only bypass.
        from app.services.documental.contracts import Provenance
        from app.services.documental.local_documents import LocalDocuments
        doc = db.get(Document, "local-" + "a" * 32)
        LocalDocuments(db, user).provenance(IDENT, doc.id, Provenance(
            expected_document_version=doc.version,
            decision="REVOKED",
            reason="Fuente de prueba revocada tras nueva inspección.",
        ))
        invalidated = editor.get(IDENT, session=user)
        assert invalidated["status"] == "READY_FOR_CHANNELS"  # historical, not silently rewritten
        assert invalidated["documentary_gate"]["ready"] is False
        assert invalidated["readiness"]["ready"] is False
        assert "documentary_primary_source" in invalidated["readiness"]["missing"]
        with pytest.raises(ValueError):
            editor.confirm_monthly_review(IDENT, 1, session=user)
        with pytest.raises(ValueError):
            editor.save(IDENT, fields, "READY_FOR_CHANNELS", 1, session=user)
