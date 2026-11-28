"""Stage4 classification uses only disposable DBs and fictitious source facts."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from sqlalchemy import select, event
from sqlalchemy.orm import Session

from app.database.models import CatalogSnapshot, EcommApiProductEdit
from app.services.documental.storage import Dossier, Document
from app.services.documental.taxonomy_catalog import (
    TaxonomyCatalog,
    catalog_state,
    SOURCE,
)
from app.services.documental.taxonomy_review import (
    TaxonomyReview,
    inspection_from_context,
)
from app.services.documental.research import Research, identity_digest
from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
from app.integrations.ecomm_app.api_catalog_browser import api_variant_row
import test_documental_taxonomy_review as fixtures
import test_documental_complete_draft_flow as source_fixture

database = fixtures.database
USER = SimpleNamespace(id=1)
PAIR = {
    "id": "seeds",
    "category": "Alimentos",
    "subcategory": "Semillas",
    "state": "ACTIVE",
}
MAPPING = {
    "id": "ml-seeds",
    "pair_id": "seeds",
    "channel": "ML",
    "category": "Almacén",
    "subcategory": "Semillas",
    "state": "ACTIVE",
}
REASON = "Revisé el vocabulario interno y las equivalencias de canal de prueba."


def prepare_catalog(
    db, *, version=0, revision="internal-test-v1", entries=None, mappings=None
):
    return TaxonomyCatalog(db, USER).save(
        expected_version=version,
        revision=revision,
        entries=entries if entries is not None else [PAIR],
        mappings=mappings if mappings is not None else [MAPPING],
        reason=REASON,
    )


def approve(db, *, channel="KIKI", overrides=None):
    service = TaxonomyReview(db, USER)
    state = service.get(source_fixture.IDENT, channel)
    catalog = catalog_state(db)
    destination = PAIR if channel == "KIKI" else MAPPING
    return service.review(
        source_fixture.IDENT,
        expected_version=state["expected_version"],
        expected_workspace_version=state["expected_workspace_version"],
        expected_fingerprint=state["evidence_fingerprint"],
        channel=channel,
        decision="APPROVED",
        taxonomy_revision=catalog["revision"],
        target_category=destination["category"],
        target_subcategory=destination["subcategory"],
        reason=REASON,
        catalog_version=catalog["version"],
        catalog_pair_id="seeds",
        channel_mapping_id=None if channel == "KIKI" else "ml-seeds",
        **(overrides or {}),
    )


def test_catalog_persistence_cas_history_and_no_product_changes(database):
    engine, stage = database
    with Session(engine) as db:
        first = prepare_catalog(db)
        assert first["version"] == 1 and len(first["history"]) == 1
        with pytest.raises(ValueError, match="otra sesión"):
            prepare_catalog(db)
        db.rollback()
        assert catalog_state(db)["fingerprint"] == first["fingerprint"]
        second = prepare_catalog(db, version=1, revision="internal-test-v2")
        assert second["version"] == 2 and len(second["history"]) == 2
        assert second["history"][0]["entries"] == first["entries"]
        assert not second["external_category_ids_verified"]
        assert db.scalar(select(EcommApiProductEdit)) is None
        assert (
            db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
                )
            ).payload
            == stage
        )
    with Session(engine) as db:
        assert TaxonomyCatalog(db, USER).get()["revision"] == "internal-test-v2"


@pytest.mark.parametrize(
    "entries,mappings",
    [
        ([PAIR, PAIR], []),
        ([PAIR], [{**MAPPING, "pair_id": "unknown"}]),
        ([{**PAIR, "state": "RETIRED"}], [MAPPING]),
        ([PAIR], [MAPPING, {**MAPPING, "id": "second"}]),
        ([PAIR], [{**MAPPING, "external_category_id": "must-not-invent"}]),
    ],
)
def test_ambiguous_or_invented_catalog_entries_are_rejected(
    database, entries, mappings
):
    engine, _ = database
    with Session(engine) as db:
        with pytest.raises(ValueError):
            prepare_catalog(db, entries=entries, mappings=mappings)
        db.rollback()
        assert catalog_state(db)["version"] == 0


def test_changed_catalog_invalidates_old_variant_suggestion_without_reapproval(
    database,
):
    engine, _ = database
    with Session(engine) as db:
        prepare_catalog(db)
        first = approve(db)
        assert first["state"] == "APPROVED" and first["catalog_bound"]
        prepare_catalog(
            db,
            version=1,
            revision="internal-test-v2",
            entries=[{**PAIR, "state": "RETIRED"}],
            mappings=[{**MAPPING, "state": "RETIRED"}],
        )
        result = TaxonomyReview(db, USER).get(source_fixture.IDENT)
        assert result["state"] == "STALE"
        assert result["record"] == first["record"]
        assert len(result["history"]) == 1


def test_channel_equivalence_requires_review_of_same_internal_variant(database):
    engine, _ = database
    with Session(engine) as db:
        prepare_catalog(db)
        with pytest.raises(ValueError, match="primero"):
            approve(db, channel="ML")
        db.rollback()
        approve(db)
        result = approve(db, channel="ML")
        assert result["record"]["internal_pair"] == {
            "category": "Alimentos",
            "subcategory": "Semillas",
        }
        assert result["record"]["target_pair"] == {
            "category": "Almacén",
            "subcategory": "Semillas",
        }
        assert result["official_external_category_verified"] is False
        assert (
            TaxonomyReview(db, USER).get(source_fixture.IDENT, "TN")["state"] == "NONE"
        )


def test_catalog_bound_classification_survives_copy_save_but_requires_workspace_cas(
    database,
):
    engine, _ = database
    with Session(engine) as db:
        prepare_catalog(db)
        approved = approve(db)
        db.add(
            EcommApiProductEdit(
                ecomm_id=source_fixture.IDENT,
                source_sku="9995",
                source_snapshot={},
                fields={"title": "Texto interno de prueba"},
                status="DRAFT",
                version=1,
                history=[],
            )
        )
        db.commit()
        state = TaxonomyReview(db, USER).get(source_fixture.IDENT)
        assert state["state"] == "APPROVED"
        assert state["evidence_fingerprint"] == approved["evidence_fingerprint"]
        assert state["expected_workspace_version"] == 1


def test_human_classification_can_cite_approved_name_and_size_not_invent_maker_category(
    database,
):
    engine, _ = database
    with Session(engine) as db:
        prepare_catalog(db)
        item = db.get(Dossier, source_fixture.IDENT)
        item.facts = [
            f for f in item.facts if f["field"] not in {"category", "subcategory"}
        ]
        db.commit()
        state = TaxonomyReview(db, USER).get(source_fixture.IDENT)
        assert state["source_pair"] is None and state["can_approve"]
        result = approve(db)
        assert result["state"] == "APPROVED" and result["record"]["source_pair"] is None
        assert len(result["record"]["evidence_ids"]) >= 2
        item.facts = [f for f in item.facts if f["field"] != "presentation"]
        db.commit()
        assert TaxonomyReview(db, USER).get(source_fixture.IDENT)["state"] == "STALE"


class LocalBulkContext:
    """SQLite equivalent of production Context's bulk loading for contract tests."""

    def __init__(self, db, ids, source, _budget, lock=False):
        self.source = source
        self.dossiers = {
            d.ecomm_id: d
            for d in db.scalars(select(Dossier).where(Dossier.ecomm_id.in_(ids)))
        }
        self.edits = {
            d.ecomm_id: d
            for d in db.scalars(
                select(EcommApiProductEdit).where(EcommApiProductEdit.ecomm_id.in_(ids))
            )
        }
        self.docs = {d.id: d for d in db.scalars(select(Document))}
        owner = self

        class Workspace(EcommApiProductWorkspace):
            def _source(self, ident):
                return owner.source[ident]

            def get(self, ident):
                return self._serialize(owner.edits.get(ident), self._source(ident))

        class BulkResearch(Research):
            workspace_type = Workspace

            def __init__(self, db, session):
                self.db, self.actor, self._document_refs = (
                    db,
                    "synthetic-reviewer",
                    owner.docs,
                )

            def edit_record(self, ident):
                return owner.edits.get(ident)

        self.Workspace, self.Research = Workspace, BulkResearch

    def inspect(self, db, session, ident):
        research = self.Research(db, session)
        edit = self.Workspace(db).get(ident)
        item = self.dossiers.get(ident) or SimpleNamespace(
            identity_digest=identity_digest(research.reference(ident)), facts=[]
        )
        authorized = [
            f
            for f in item.facts
            if f["state"] == "APPROVED" and not research.blockers(item, f)
        ]
        docs = [
            d for d in self.docs.values() if d.body.get("associated_ecomm_id") == ident
        ]
        result = inspection_from_context(ident, item, edit, authorized, docs, {})
        result["name"] = edit["source"]["product_name"]
        return result

    def release(self):
        pass


def local_source(db, lock=False):
    row = db.scalar(
        select(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP_API_STAGE")
    )
    return {
        str(v["id"]): api_variant_row(p, v, page["captured_at"])
        for page in row.payload
        for p in page["items"]
        for v in p["variants"]
    }


def add_without_document(db, count=1):
    row = db.scalar(
        select(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP_API_STAGE")
    )
    pages = deepcopy(row.payload)
    for index in range(count):
        variant = deepcopy(pages[0]["items"][0]["variants"][0])
        variant.update(id=f"EXCEPTION-{index}", sku=f"EXCEPTION-SKU-{index}")
        pages[0]["items"][0]["variants"].append(variant)
    row.payload = pages
    db.commit()


def decision(preview, ident):
    row = next(r for r in preview["items"] if r["ecomm_id"] == ident)
    return {
        "ecomm_id": ident,
        "decision": "APPROVED",
        "expected_version": row["expected_version"],
        "expected_workspace_version": row["expected_workspace_version"],
        "expected_fingerprint": row["evidence_fingerprint"],
        "taxonomy_revision": preview["catalog"]["revision"],
        "target_category": PAIR["category"],
        "target_subcategory": PAIR["subcategory"],
        "reason": REASON,
        "catalog_version": preview["catalog"]["version"],
        "catalog_pair_id": "seeds",
    }


def test_batch_atomic_recovery_skips_exceptions_and_does_not_overwrite_fiches(database):
    engine, _ = database
    with Session(engine) as db:
        prepare_catalog(db)
        add_without_document(db)
        service = TaxonomyReview(db, USER)
        ids = [source_fixture.IDENT, "EXCEPTION-0"]
        preview = service.preview_batch(
            ids, context_type=LocalBulkContext, source_loader=local_source
        )
        assert preview["items"][1]["exception"] == "REVIEW_REQUIRED"
        choices = [decision(preview, ident) for ident in ids]
        with pytest.raises(ValueError, match="documentación"):
            service.review_batch(
                ids=ids,
                channel="KIKI",
                expected_selection_fingerprint=preview["selection_fingerprint"],
                decisions=choices,
                context_type=LocalBulkContext,
                source_loader=local_source,
            )
        assert service.get(source_fixture.IDENT)["state"] == "NONE"
        preview = service.preview_batch(
            ids, context_type=LocalBulkContext, source_loader=local_source
        )
        choices = [
            decision(preview, ids[0]),
            {
                "ecomm_id": ids[1],
                "decision": "SKIP",
                "reason": "Falta el documento original.",
            },
        ]
        result = service.review_batch(
            ids=ids,
            channel="KIKI",
            expected_selection_fingerprint=preview["selection_fingerprint"],
            decisions=choices,
            context_type=LocalBulkContext,
            source_loader=local_source,
        )
        assert [r["state"] for r in result["items"]] == ["APPROVED", "SKIPPED"]
        assert db.scalar(select(EcommApiProductEdit)) is None
        with pytest.raises(ValueError, match="Cambió"):
            service.review_batch(
                ids=ids,
                channel="KIKI",
                expected_selection_fingerprint=preview["selection_fingerprint"],
                decisions=choices,
                context_type=LocalBulkContext,
                source_loader=local_source,
            )


def test_batch_bounds_coverage_and_constant_query_count(database):
    engine, _ = database
    with Session(engine) as db:
        prepare_catalog(db)
        add_without_document(db, 20)
        service = TaxonomyReview(db, USER)
        with pytest.raises(ValueError):
            service.preview_batch(
                ["EXCEPTION-0"] * 2,
                context_type=LocalBulkContext,
                source_loader=local_source,
            )
        with pytest.raises(ValueError):
            service.preview_batch(
                [source_fixture.IDENT] + [f"EXCEPTION-{i}" for i in range(20)],
                context_type=LocalBulkContext,
                source_loader=local_source,
            )
        counts = []
        for ids in (
            [source_fixture.IDENT],
            [source_fixture.IDENT] + [f"EXCEPTION-{i}" for i in range(19)],
        ):
            queries = []

            def track(_conn, _cursor, statement, *_args):
                if statement.lstrip().upper().startswith("SELECT"):
                    queries.append(statement)

            event.listen(engine, "before_cursor_execute", track)
            try:
                preview = service.preview_batch(
                    ids, context_type=LocalBulkContext, source_loader=local_source
                )
            finally:
                event.remove(engine, "before_cursor_execute", track)
            counts.append(len(queries))
            assert preview["total"] == len(ids)
        assert counts[0] == counts[1]


def test_catalog_payload_size_and_integrity_fail_closed(database, monkeypatch):
    import app.services.documental.taxonomy_catalog as module

    engine, _ = database
    with Session(engine) as db:
        monkeypatch.setattr(module, "MAX_BYTES", 1)
        with pytest.raises(ValueError, match="5 MiB"):
            prepare_catalog(db)
        db.rollback()
        assert catalog_state(db)["version"] == 0
        monkeypatch.setattr(module, "MAX_BYTES", 5 * 1024 * 1024)
        prepare_catalog(db)
        row = db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == SOURCE))
        payload = deepcopy(row.payload)
        payload[0]["entries"][0]["category"] = "Alteración sin revisión"
        row.payload = payload
        db.commit()
        with pytest.raises(ValueError, match="integridad"):
            catalog_state(db)


def test_generation_reuses_human_mapping_and_existing_versioned_editor(database):
    """No generator/provider is replaced: review and apply the real proposal."""
    from app.services.documental.proposals import Proposals
    from app.services.ecomm_api_product_workspace_service import blank_fields

    engine, _ = database
    with Session(engine) as db:
        prepare_catalog(db)
        mapping = approve(db)
        service = Proposals(db, USER)
        proposal = service.generate(source_fixture.IDENT, 0)
        decisions = {}
        for key, label in (
            ("category", PAIR["category"]),
            ("subcategory", PAIR["subcategory"]),
        ):
            value = proposal["fields"][key]
            assert value["value"] == label
            assert value["evidence_kind"] == "INTERNAL_TAXONOMY_DECISION"
            assert value["evidence_ids"] == mapping["record"]["evidence_ids"]
            assert value["taxonomy_revision"] == "internal-test-v1"
            decisions[key] = {"decision": "ACCEPTED", "value": label}
        assert (
            proposal["fields"]["category"]["value"]
            != mapping["record"]["source_pair"]["category"]
        )
        assert "seo_keywords" not in proposal["fields"]
        reviewed = service.review(
            source_fixture.IDENT, proposal["draft_id"], proposal["revision"], decisions
        )
        merged = blank_fields()
        merged.update(category=PAIR["category"], subcategory=PAIR["subcategory"])
        saved = service.apply(
            source_fixture.IDENT,
            proposal["draft_id"],
            reviewed["revision"],
            SimpleNamespace(
                expected_version=0,
                status="DRAFT",
                fields=SimpleNamespace(model_dump=lambda: merged),
            ),
        )
        assert saved["version"] == 1 and saved["status"] == "DRAFT"
        assert saved["fields"]["category"] == PAIR["category"]
        assert TaxonomyReview(db, USER).get(source_fixture.IDENT)["state"] == "APPROVED"


def test_taxonomy_change_invalidates_previously_generated_proposal(database):
    from app.services.documental.proposals import Proposals

    engine, _ = database
    with Session(engine) as db:
        prepare_catalog(db)
        approve(db)
        service = Proposals(db, USER)
        proposal = service.generate(source_fixture.IDENT, 0)
        prepare_catalog(db, version=1, revision="internal-test-v2")
        with pytest.raises(ValueError, match="desactualizada"):
            service.review(
                source_fixture.IDENT,
                proposal["draft_id"],
                proposal["revision"],
                {
                    "category": {"decision": "ACCEPTED", "value": PAIR["category"]},
                },
            )
        assert TaxonomyReview(db, USER).get(source_fixture.IDENT)["state"] == "STALE"


def test_catalog_api_keeps_session_csrf_confirmation_and_feature_gate(
    database, monkeypatch
):
    from datetime import datetime, timedelta, timezone
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routes import documental_workspace as routes
    from app.core import security
    from app.database.models import AdminSession
    from app.database.session import get_db

    engine, stage = database
    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(kiki_document_workspace_enabled=True),
    )
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(app_session_secret="synthetic-only-taxonomy-secret"),
    )
    cookie = "synthetic-taxonomy-session"
    checksum = security.token_hash(cookie)
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        db.add(
            AdminSession(
                token_hash=checksum,
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
        db.commit()

    def local_db():
        with Session(engine) as db:
            yield db

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = local_db
    path = "/api/ecomm-app/workspace/taxonomy/catalog"
    data = {
        "expected_version": 0,
        "revision": "internal-test-v1",
        "entries": [PAIR],
        "mappings": [MAPPING],
        "reason": REASON,
        "confirm": True,
    }
    with TestClient(app) as client:
        assert client.get(path).status_code == 401
        client.cookies.set(security.SESSION_COOKIE, cookie)
        assert client.get(path).json()["version"] == 0
        assert client.post(path, json=data).status_code == 403
        headers = {"X-CSRF-Token": security.csrf_token(checksum)}
        assert (
            client.post(
                path, json={**data, "confirm": False}, headers=headers
            ).status_code
            == 422
        )
        saved = client.post(path, json=data, headers=headers)
        assert saved.status_code == 200 and saved.json()["version"] == 1
        assert saved.json()["external_category_ids_verified"] is False
        assert client.post(path, json=data, headers=headers).status_code == 409
        monkeypatch.setattr(
            routes,
            "get_settings",
            lambda: SimpleNamespace(kiki_document_workspace_enabled=False),
        )
        assert client.get(path).status_code == 403
    with Session(engine) as db:
        assert db.scalar(select(EcommApiProductEdit)) is None
        assert (
            db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source == "ECOMM_APP_API_STAGE"
                )
            ).payload
            == stage
        )
