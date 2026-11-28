"""Stage-4 review packages use real services and wholly fictional local inputs."""
from copy import deepcopy
import csv
from datetime import datetime, timedelta, timezone
from io import StringIO
from types import SimpleNamespace

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.database.models import CatalogSnapshot, EcommApiProductEdit
from app.services.commercial_channel_export_service import preview_commercial_export, download_commercial_export
from app.services.documental.media_rights import review_media_rights
from app.services.documental.research import Research
from app.services.documental.storage import Dossier
from app.services.documental.taxonomy_catalog import TaxonomyCatalog
from app.services.documental.taxonomy_review import TaxonomyReview
from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
from test_documental_channel_readiness_guard import IDENT, prepare, install_fake_source, complete_fields, setting

USER = SimpleNamespace(id=1)
PAIR = "synthetic-food"


def edit_for(db):
    return db.scalar(select(EcommApiProductEdit).where(EcommApiProductEdit.ecomm_id == IDENT))


def catalog_arguments():
    return {
        "entries": [{"id": PAIR, "category": "Categoría de prueba", "subcategory": "Subcategoría de prueba", "state": "ACTIVE"}],
        "mappings": [{"id": "synthetic-" + channel.lower(), "pair_id": PAIR, "channel": channel, "category": "Categoría " + channel, "subcategory": "Subcategoría " + channel, "state": "ACTIVE"} for channel in ("ML", "TN")],
    }


def approve_mapping(db, channel, *, decision="APPROVED"):
    service = TaxonomyReview(db, USER)
    state = service.get(IDENT, channel)
    category, subcategory = ("Categoría de prueba", "Subcategoría de prueba") if channel == "KIKI" else ("Categoría " + channel, "Subcategoría " + channel)
    return service.review(
        IDENT, expected_version=state["expected_version"], expected_workspace_version=state["expected_workspace_version"],
        expected_fingerprint=state["evidence_fingerprint"], channel=channel, decision=decision,
        taxonomy_revision="synthetic-v1", target_category=category, target_subcategory=subcategory,
        reason="Explicit human review of this fictional category pair and variant.",
        catalog_version=1, catalog_pair_id=PAIR,
        channel_mapping_id="synthetic-" + channel.lower() if channel != "KIKI" else None,
    )


def bind_media(db):
    research = Research(db, USER)
    case = research.dossier(IDENT)
    doc = research._document("local-" + "a" * 32)
    edit = db.scalar(select(EcommApiProductEdit).where(EcommApiProductEdit.ecomm_id == IDENT))
    media = edit.fields["media"][0]
    review_media_rights(
        research, IDENT, case.version, doc.id, doc.version,
        media["url"], media["kind"], media["source_url"], "APPROVED", "OWNER_AUTHORIZATION",
        "texto/linea/6", doc.body["sections"]["texto/linea/6"],
        "Human inspection of the fictional licence for this exact saved resource.",
        alt_text=media["alt"], presentation=edit.fields["presentation"],
        expected_workspace_version=edit.version,
        valid_until=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
    )


@pytest.fixture
def database(tmp_path, monkeypatch):
    import app.services.documental.research as module
    monkeypatch.setattr(module, "get_settings", lambda: setting())
    engine, _ = prepare(tmp_path)
    with Session(engine) as db:
        install_fake_source(db)
        EcommApiProductWorkspace(db).save(IDENT, complete_fields(), "READY_FOR_CHANNELS", 0, session=USER)
    yield engine
    engine.dispose()


def prepare_reviewed(db):
    bind_media(db)
    TaxonomyCatalog(db, USER).save(expected_version=0, revision="synthetic-v1", reason="Human acceptance of a fictional versioned vocabulary.", **catalog_arguments())
    for channel in ("KIKI", "ML", "TN"):
        approve_mapping(db, channel)


@pytest.mark.parametrize("channel", ["ml", "tn"])
def test_full_reviewed_channel_package_has_citations_and_no_provider_or_data_writes(database, channel):
    with Session(database) as db:
        prepare_reviewed(db)
    writes = []
    def track(_conn, _cursor, statement, *_rest):
        if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            writes.append(statement)
    event.listen(database, "before_cursor_execute", track)
    try:
        with Session(database) as db:
            before = deepcopy(edit_for(db).fields)
            dossier_history = deepcopy(db.get(Dossier, IDENT).history)
            preview = preview_commercial_export(db, USER, channel, [IDENT])
            assert preview["prepared_internal"] == 1
            assert preview["blocked"] == 0
            item = preview["items"][0]
            assert item["internal_taxonomy"]["catalog_bound"] is True
            assert item["channel_taxonomy"]["catalog_bound"] is True
            assert item["channel_taxonomy"]["target_pair"]["category"] == "Categoría " + channel.upper()
            assert item["channel_taxonomy"]["external_category_ids"] is None
            assert item["field_evidence"]["seo_title"]
            assert item["publication_enabled"] is False
            content, repeated = download_commercial_export(db, USER, channel, [IDENT], preview["preview_fingerprint"])
            assert repeated["prepared_internal"] == 1
            row = list(csv.DictReader(StringIO(content.decode("utf-8-sig")), delimiter=";"))[0]
            assert row["ecomm_id"] == IDENT
            assert row["par_interno_id"] == PAIR
            assert row["mapeo_canal_id"] == "synthetic-" + channel
            assert row["publicacion_habilitada"] == row["formato_nativo_proveedor"] == "NO"
            assert "price" not in row and "stock" not in row and "cost" not in row
            assert edit_for(db).fields == before
            assert db.get(Dossier, IDENT).history == dossier_history
            assert preview["provider_calls"] == preview["ai_requests"] == 0
        assert writes == []
    finally:
        event.remove(database, "before_cursor_execute", track)


@pytest.mark.parametrize("reviewed", [(), ("KIKI",), ("KIKI", "ML")])
def test_internal_and_each_channel_require_separate_bound_human_mappings(database, reviewed):
    with Session(database) as db:
        bind_media(db)
        TaxonomyCatalog(db, USER).save(expected_version=0, revision="synthetic-v1", reason="Human acceptance of a fictional versioned vocabulary.", **catalog_arguments())
        for channel in reviewed:
            approve_mapping(db, channel)
        preview = preview_commercial_export(db, USER, "tn", [IDENT])
        assert preview["items"][0]["state"] == "BLOCKED"
        assert any("clasificación interna" in reason or "equivalencia" in reason for reason in preview["items"][0]["blockers"])


@pytest.mark.parametrize("change", ["catalog", "internal-revoked", "channel-revoked", "uncited-seo", "rights", "duplicate-code", "parent-pack"])
def test_preview_is_invalidated_by_mapping_rights_copy_or_identity_changes(database, change):
    with Session(database) as db:
        prepare_reviewed(db)
        preview = preview_commercial_export(db, USER, "ml", [IDENT])
        assert preview["prepared_internal"] == 1
        if change == "catalog":
            TaxonomyCatalog(db, USER).save(expected_version=1, revision="synthetic-v2", reason="Human revision of the fictional taxonomy catalogue.", **catalog_arguments())
        elif change in {"internal-revoked", "channel-revoked"}:
            approve_mapping(db, "KIKI" if change == "internal-revoked" else "ML", decision="REVOKED")
        elif change in {"uncited-seo", "rights"}:
            edit = edit_for(db)
            fields = deepcopy(edit.fields)
            if change == "uncited-seo":
                fields["seo_description"] += " Beneficio de salud inventado."
            else:
                fields["media"][0]["alt"] = "Texto alternativo no autorizado"
            edit.fields = fields
            db.commit()
        else:
            snapshot = db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP_API_STAGE"))
            pages = deepcopy(snapshot.payload)
            if change == "parent-pack":
                pages[0]["items"][0]["is_combo"] = True
            else:
                first = pages[0]["items"][0]["variants"][0]
                first["barcode"] = "036000291452"
                other = deepcopy(first)
                other.update(id="7518950", sku="SYNTHETIC-SECOND-VARIANT")
                pages[0]["items"][0]["variants"].append(other)
            snapshot.payload = pages
            db.commit()
        changed = preview_commercial_export(db, USER, "ml", [IDENT])
        assert changed["items"][0]["state"] == "BLOCKED"
        with pytest.raises(ValueError, match="previsualización"):
            download_commercial_export(db, USER, "ml", [IDENT], preview["preview_fingerprint"])


def test_natural_seed_equivalent_incomplete_draft_v6_is_preserved_and_blocked(database):
    with Session(database) as db:
        edit = edit_for(db)
        edit.status, edit.version = "DRAFT", 6
        fields = deepcopy(edit.fields)
        fields["category"] = fields["subcategory"] = ""
        fields["seo_description"] = "Texto comercial editado, todavía sin revisar."
        edit.fields = fields
        dossier = db.get(Dossier, IDENT)
        dossier.facts = [fact for fact in dossier.facts if fact["field"] in {"product_name", "presentation", "characteristics"}]
        dossier.history = [entry for entry in dossier.history if entry.get("action") != "MEDIA_RIGHTS_REVIEW"]
        db.commit()
        before = deepcopy((edit.fields, edit.history, dossier.facts, dossier.history))
        for channel in ("ml", "tn"):
            result = preview_commercial_export(db, USER, channel, [IDENT])
            assert result["prepared_internal"] == 0
            assert result["items"][0]["state"] == "BLOCKED"
            download_commercial_export(db, USER, channel, [IDENT], result["preview_fingerprint"])
        assert (edit.status, edit.version) == ("DRAFT", 6)
        assert (edit.fields, edit.history, dossier.facts, dossier.history) == before
