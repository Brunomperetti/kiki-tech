"""Offline synthetic coverage tests; no fixture is customer approval or a licence."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.services.documental.completion import SAVED_STATES, saved_field_coverage
from app.services.documental.evidence_ai import EVENT as AI_EVENT, MODEL as AI_MODEL
from app.services.documental.proposals import Proposals
from app.services.ecomm_api_product_workspace_service import FIELDS, blank_fields

IDENT = "7518949"
URL = "https://fabricante-sintetico.invalid/producto"


class SyntheticResearch:
    def __init__(self, facts):
        self.edit = SimpleNamespace(version=6, source_sku="9995")
        self.source = {"sku": "9995", "identity_blockers": []}
        self.doc = SimpleNamespace(
            body={
                "original": {"sha256": "a" * 64},
                "source": {"reference_url": URL},
            }
        )
        self.item = SimpleNamespace(
            ecomm_id=IDENT, identity_digest="identity", facts=facts, history=[]
        )
        self.invalid = set()

    def edit_record(self, ident):
        assert ident == IDENT
        return self.edit

    def source_record(self, ident):
        assert ident == IDENT
        return self.source

    def blockers(self, item, fact):
        return (
            ["Fuente cambió: revisión necesaria."] if fact["id"] in self.invalid else []
        )

    def _document(self, ident):
        assert ident == "documento-sintetico"
        return self.doc


def fact(key, value, number):
    return {
        "id": f"fact-{number}",
        "field": key,
        "value": value,
        "unit": None,
        "state": "APPROVED",
        "ecomm_id": IDENT,
        "version": 1,
        "identity_hash": "identity",
        "presentation": "250 g",
        "document_id": "documento-sintetico",
        "document_version": 1,
        "document_hash": "b" * 64,
        "quote": f"{key}: {value}",
        "location": f"texto/linea/{number}",
        "commercial_field": "attributes",
    }


def context():
    return SyntheticResearch(
        [
            fact("product_name", "Mix Ensaladas y Sopas", 1),
            fact("presentation", "250 g", 2),
            fact("characteristics", "3 frutos secos y 3 semillas", 3),
        ]
    )


def report(research, fields, **kwargs):
    result = saved_field_coverage(
        research,
        research.item,
        fields,
        applied_proposals=kwargs.pop("applied_proposals", []),
        **kwargs,
    )
    assert (
        result["ecomm_id"] == IDENT
        and result["workspace_version"] == research.edit.version
    )
    assert result["total_fields"] == len(FIELDS) == 18
    assert set(result["states"]) == set(SAVED_STATES)
    assert sum(result["states"].values()) == 18
    assert {row["field"] for row in result["fields"]} == set(FIELDS)
    assert result["publication_allowed"] is False
    assert result["commercial_completion_certified"] is False
    return {row["field"]: row for row in result["fields"]}


def generated_fields(research):
    generated, _ = Proposals.generate_fields(research.item.facts)
    return {**blank_fields(), **{key: row["value"] for key, row in generated.items()}}


def test_natural_seed_shape_does_not_gain_brand_category_or_media_approval_from_saved_text():
    research = context()
    fields = generated_fields(research)
    fields.update(
        brand="Natural Seed",
        manufacturer="Natural Seed",
        category="Semillas",
        seo_description="Una opción saludable sin gluten",
    )
    fields["media"] = [
        {"kind": "IMAGE", "url": URL + "/imagen.png", "source_url": URL, "alt": "Mix"}
    ]
    before = deepcopy(fields)
    rows = report(research, fields)
    assert rows["title"]["state"] == "APPROVED_BACKED"
    assert {c["fact_id"] for c in rows["title"]["citations"]} == {"fact-1", "fact-2"}
    assert all(
        c["current"] and c["document_sha256"] == "a" * 64
        for c in rows["title"]["citations"]
    )
    assert rows["brand"]["state"] == rows["manufacturer"]["state"] == "FILLED_UNBACKED"
    assert rows["category"]["state"] == "FILLED_UNBACKED"
    assert rows["seo_description"]["state"] == "FILLED_UNBACKED"
    assert rows["media"]["state"] == "BLOCKED"
    assert rows["proposed_gtin"]["state"] == "PENDING_REVIEW"
    assert fields == before and research.edit.version == 6


@pytest.mark.parametrize("state", ["REVOKED", "STALE"])
def test_revoked_and_changed_sources_are_not_current_backing(state):
    research = context()
    fields = generated_fields(research)
    research.item.facts[0]["state"] = state
    rows = report(research, fields)
    assert rows["title"]["state"] == "BLOCKED"
    assert not rows["title"]["evidence_ids"] and not rows["title"]["citations"]
    research = context()
    research.invalid.add("fact-1")
    assert report(research, fields)["description"]["state"] == "BLOCKED"


def test_changed_sku_and_variant_conflict_block_every_field():
    research = context()
    fields = generated_fields(research)
    research.source["sku"] = "otro-sku"
    assert {row["state"] for row in report(research, fields).values()} == {"BLOCKED"}
    research = context()
    research.source["identity_blockers"] = ["Barcode y GTIN discrepan."]
    assert {row["state"] for row in report(research, fields).values()} == {"BLOCKED"}


def test_internal_taxonomy_uses_explicit_current_decision_not_manufacturer_label():
    research = context()
    fields = {**blank_fields(), "category": "Almacén", "subcategory": "Semillas"}
    mapping = {
        "state": "APPROVED",
        "catalog_bound": True,
        "mapping_version": 3,
        "record": {
            "review_kind": "HUMAN_EXPLICIT",
            "ecomm_id": IDENT,
            "identity_hash": "identity",
            "evidence_ids": ["fact-1", "fact-2"],
            "target_pair": {"category": "Almacén", "subcategory": "Semillas"},
            "taxonomy_revision": "kiki-sintetica-v1",
            "reviewer": "operador-sintetico",
            "reason": "Decisión interna de prueba.",
        },
    }
    rows = report(research, fields, taxonomy=mapping)
    for key in ("category", "subcategory"):
        assert rows[key]["state"] == "APPROVED_BACKED"
        assert rows[key]["lineage"]["evidence_kind"] == "INTERNAL_TAXONOMY_DECISION"
        assert rows[key]["lineage"]["reviewer"] == "operador-sintetico"
    mapping["state"] = "STALE"
    assert report(research, fields, taxonomy=mapping)["category"]["state"] == "BLOCKED"


def applied_ai(research, value):
    ids = ["fact-1", "fact-2"]
    proposal = {"value": value, "evidence_ids": ids, "clauses": [value]}
    decision = {"decision": "ACCEPTED", "value": value}
    return {
        "id": 42,
        "product_key": "ECOMM_DOCUMENTAL:" + IDENT,
        "model": AI_MODEL,
        "review_status": "APPLIED",
        "source_facts": deepcopy(research.item.facts),
        "history": [
            {
                "event": AI_EVENT,
                "proposal": {
                    "identity_hash": "identity",
                    "ai_fields": ["description"],
                    "fields": {"description": proposal},
                    "decisions": {"description": decision},
                },
            },
            {
                "event": "FIELD_REVIEW",
                "actor": "revision-humana-sintetica",
                "decisions": {"description": decision},
            },
            {
                "event": "APPLIED_VIA_WORKSPACE",
                "actor": "operador-sintetico",
                "selected_fields": ["description"],
                "workspace_version_before": 4,
            },
        ],
    }


def test_reviewed_expressive_copy_survives_own_apply_but_not_changed_facts_or_wrong_identity():
    research = context()
    value = "Mix Ensaladas y Sopas en presentación de 250 g."
    record = applied_ai(research, value)
    fields = {**blank_fields(), "description": value}
    rows = report(research, fields, applied_proposals=[record])
    assert rows["description"]["state"] == "APPROVED_BACKED"
    assert rows["description"]["lineage"]["draft_id"] == 42
    research.edit.version += (
        1  # Later unrelated save cannot invalidate unchanged reviewed copy.
    )
    assert (
        report(research, fields, applied_proposals=[record])["description"]["state"]
        == "APPROVED_BACKED"
    )
    research.item.facts[0]["version"] += 1
    assert (
        report(research, fields, applied_proposals=[record])["description"]["state"]
        != "APPROVED_BACKED"
    )
    research.item.facts[0]["version"] = 1
    record["history"][0]["proposal"]["identity_hash"] = "another-variant"
    assert (
        report(research, fields, applied_proposals=[record])["description"]["state"]
        != "APPROVED_BACKED"
    )


@pytest.mark.parametrize(
    "change", ["no-human", "no-apply", "wrong-variant", "unsupported", "pending-fact"]
)
def test_old_applied_flag_is_not_sufficient(change):
    research = context()
    value = "Mix Ensaladas y Sopas en presentación de 250 g."
    record = applied_ai(research, value)
    if change == "no-human":
        record["history"][1]["actor"] = ""
    elif change == "no-apply":
        record["history"].pop()
    elif change == "wrong-variant":
        record["product_key"] += "0"
    elif change == "unsupported":
        value += " Sin gluten."
        record = applied_ai(research, value)
    elif change == "pending-fact":
        research.item.facts[0]["state"] = "PENDING"
    row = report(
        research, {**blank_fields(), "description": value}, applied_proposals=[record]
    )["description"]
    assert row["state"] != "APPROVED_BACKED"


def test_sources_verified_checkbox_alone_cannot_back_editor_sources():
    research = context()
    fields = {
        **blank_fields(),
        "sources": [
            {
                "name": "Fuente",
                "url": URL,
                "kind": "FABRICANTE",
                "verified": True,
                "note": "",
            }
        ],
    }
    assert report(research, fields)["sources"]["state"] == "APPROVED_BACKED"
    research.invalid.update(f["id"] for f in research.item.facts)
    assert report(research, fields)["sources"]["state"] == "FILLED_UNBACKED"


def test_media_metadata_is_required_for_every_resource_not_only_legacy_current_flag(
    monkeypatch,
):
    import app.services.documental.media_rights as rights

    research = context()
    fields = {
        **blank_fields(),
        "media": [
            {"kind": "IMAGE", "url": URL + "/imagen", "source_url": URL, "alt": "Mix"}
        ],
    }
    permission = {
        "state": "APPROVED_CURRENT",
        "current": True,
        "stage4_ready": False,
        "document_id": "documento-sintetico",
        "document_version": 1,
        "document_hash": "b" * 64,
        "original_sha256": "a" * 64,
        "quote": "Licencia comercial ficticia de prueba.",
        "location": "texto/linea/10",
    }
    monkeypatch.setattr(rights, "media_permission_report", lambda *_: [permission])
    assert report(research, fields)["media"]["state"] == "BLOCKED"
    permission["stage4_ready"] = True
    row = report(research, fields)["media"]
    assert row["state"] == "APPROVED_BACKED"
    assert row["citations"][0]["evidence_kind"] == "MEDIA_RIGHTS"
    assert row["evidence_ids"] == []
    permission["current"] = False
    assert report(research, fields)["media"]["state"] == "BLOCKED"
    monkeypatch.setattr(rights, "media_permission_report", lambda *_: [])
    assert report(research, fields)["media"]["state"] == "BLOCKED"


def test_contradiction_cannot_be_hidden_by_an_older_applied_proposal_subset():
    research = context()
    value = "Mix Ensaladas y Sopas en presentación de 250 g."
    record = applied_ai(research, value)
    research.item.facts.append(fact("presentation", "500 g", 4))
    fields = {**blank_fields(), "description": value, "presentation": "250 g"}
    rows = report(research, fields, applied_proposals=[record])
    assert rows["description"]["state"] == "BLOCKED"
    assert rows["presentation"]["state"] == "BLOCKED"
    assert not rows["description"]["citations"]


@pytest.mark.parametrize(
    "code,state",
    [
        ("0075678164125", "APPROVED_BACKED"),
        ("7794940000796", "APPROVED_BACKED"),
        ("7794940000797", "BLOCKED"),
    ],
)
def test_documentary_gtin_preserves_leading_zero_and_checks_checksum(code, state):
    research = context()
    research.item.facts.append(fact("ean", code, 4))
    fields = {**blank_fields(), "proposed_gtin": code}
    row = report(research, fields)["proposed_gtin"]
    assert row["state"] == state
    assert fields["proposed_gtin"] == code


def test_saved_editor_reopens_and_approved_applied_ai_lineage_uses_same_persistence(
    tmp_path, monkeypatch
):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from app.database.models import EcommApiProductEdit, KikiAiEditorialDraft
    from app.services.documental.research import Research
    from app.services.ecomm_api_product_workspace_service import (
        EcommApiProductWorkspace,
    )
    from test_documental_media_rights import case
    from test_documental_channel_readiness_guard import install_fake_source

    engine = case(tmp_path, monkeypatch)
    value = "Mix Ensaladas y Sopas en presentación de 250 g."
    with Session(engine) as db:
        _doc, user = install_fake_source(db)
        research = Research(db, user)
        item = research.dossier(IDENT)
        ids = [
            f["id"]
            for f in item.facts
            if f["field"] in {"product_name", "presentation"}
        ]
        source_facts = deepcopy(item.facts)
        proposal = {"value": value, "evidence_ids": ids, "clauses": [value]}
        decision = {"decision": "ACCEPTED", "value": value}
        record = KikiAiEditorialDraft(
            product_key="ECOMM_DOCUMENTAL:" + IDENT,
            source_hash="f" * 64,
            original_name="Producto de prueba",
            source_facts=source_facts,
            model=AI_MODEL,
            title="",
            description=value,
            questions=[],
            review_status="APPLIED",
            history=[
                {
                    "event": AI_EVENT,
                    "proposal": {
                        "identity_hash": item.identity_digest,
                        "ai_fields": ["description"],
                        "fields": {"description": proposal},
                        "decisions": {"description": decision},
                    },
                },
                {
                    "event": "FIELD_REVIEW",
                    "actor": "operador-sintetico",
                    "decisions": {"description": decision},
                },
                {
                    "event": "APPLIED_VIA_WORKSPACE",
                    "actor": "operador-sintetico",
                    "selected_fields": ["description"],
                    "workspace_version_before": 0,
                },
            ],
        )
        db.add(record)
        saved = EcommApiProductWorkspace(db).save(
            IDENT, {**blank_fields(), "description": value}, "DRAFT", 0
        )
        assert saved["version"] == 1
    with Session(engine) as db:
        research = Research(db, user)
        saved = db.scalar(select(EcommApiProductEdit))
        history_before = deepcopy(saved.history)
        coverage = saved_field_coverage(research, research.dossier(IDENT), saved.fields)
        row = next(r for r in coverage["fields"] if r["field"] == "description")
        assert row["state"] == "APPROVED_BACKED"
        assert row["lineage"]["draft_id"] == db.scalar(select(KikiAiEditorialDraft.id))
        assert coverage["workspace_version"] == 1
        assert saved.status == "DRAFT" and saved.history == history_before
        current = research.dossier(IDENT)
        original = next(f for f in current.facts if f["field"] == "product_name")
        research.review(
            IDENT,
            current.version,
            original["id"],
            original["version"],
            "REVOKED",
            "Revocación sintética explícita de la prueba de persistencia.",
        )
        coverage = saved_field_coverage(research, research.dossier(IDENT), saved.fields)
        assert (
            next(r for r in coverage["fields"] if r["field"] == "description")["state"]
            == "BLOCKED"
        )
        assert saved.fields["description"] == value and saved.history == history_before


def test_deterministic_saved_copy_retains_actual_individual_human_review_lineage():
    from app.services.documental.proposals import EVENT, MODEL

    research = context()
    value = "Mix Ensaladas y Sopas · 250 g."
    record = applied_ai(research, value)
    record["model"] = MODEL
    record["history"][0]["event"] = EVENT
    record["history"][0]["proposal"]["ai_fields"] = []
    fields = {**blank_fields(), "description": value}
    row = report(research, fields, applied_proposals=[record])["description"]
    assert row["state"] == "APPROVED_BACKED"
    assert row["field_review_required"] is False
    assert row["lineage"]["reviewer"] == "revision-humana-sintetica"
