"""Synthetic offline acceptance of source-backed completion and media validity.

No test here constitutes customer approval, a manufacturer's licence or proof
of real product coverage. All databases, files and permissions are fabricated.
"""

import base64
from copy import deepcopy
from hashlib import sha256

import pytest
from sqlalchemy.orm import Session

from app.services.documental.completion import proposal_completion
from app.services.documental.media_rights import (
    media_permission_report,
    review_media_rights,
)
from app.services.documental.proposals import Proposals
from app.services.documental.research import Research
from app.services.documental.storage import Document, digest
from app.services.ecomm_api_product_workspace_service import (
    EcommApiProductWorkspace,
    FIELDS,
    blank_fields,
)
from test_documental_channel_readiness_guard import (
    IDENT,
    URL,
    complete_fields,
    install_fake_source,
)
from test_documental_media_rights import case


def fact(field, value, ident, unit=None):
    return {"field": field, "value": value, "id": ident, "unit": unit}


def rows(completion):
    assert completion["total_fields"] == len(FIELDS) == 18
    assert sum(completion["states"].values()) == 18
    assert {row["field"] for row in completion["fields"]} == set(FIELDS)
    assert completion["commercial_completion_certified"] is False
    assert completion["channel_ready"] is False
    return {row["field"]: row for row in completion["fields"]}


def test_all_eighteen_fields_explain_missing_and_existing_content_without_certifying():
    saved = {**blank_fields(), "brand": "Marca escrita sin respaldo"}
    result = rows(proposal_completion({}, saved, {}, [], current=True))
    assert result["brand"]["state"] == "EXISTING_CONTENT_UNVERIFIED"
    assert result["brand"]["current_evidence_supported"] is False
    assert result["description"]["state"] == "NEEDS_APPROVED_EVIDENCE"
    assert result["media"]["state"] == "MANUAL_RESOURCE_REVIEW_REQUIRED"
    assert result["sources"]["state"] == "MANUAL_SOURCE_REVIEW_REQUIRED"
    assert result["proposed_gtin"]["state"] == "API_CODE_REVIEW_REQUIRED"


def test_equivalent_sources_retain_every_citation_without_changing_copy():
    facts = [
        fact("product_name", "Producto de prueba", "name-a"),
        fact("presentation", "250 g", "size"),
        fact("product_name", "Producto de prueba", "name-b"),
    ]
    fields, _ = Proposals.generate_fields(facts)
    assert fields["title"]["value"] == "Producto de prueba · 250 g"
    assert fields["title"]["evidence_ids"] == ["name-a", "name-b", "size"]
    assert fields["short_title"]["evidence_ids"] == ["name-a", "name-b"]


@pytest.mark.parametrize("other,unit", [("Otro producto", None), ("Producto", "g")])
def test_generator_refuses_arbitrary_selection_between_conflicting_approved_values(
    other, unit
):
    with pytest.raises(ValueError, match="contradictorios"):
        Proposals.generate_fields(
            [
                fact("product_name", "Producto", "a"),
                fact("product_name", other, "b", unit),
                fact("presentation", "250 g", "size"),
            ]
        )


def test_decisions_and_staleness_are_separate_from_saved_fields():
    proposed = {
        key: {"value": "Texto", "evidence_ids": ["a"]}
        for key in ("title", "description", "short_title")
    }
    decisions = {
        "title": {"decision": "ACCEPTED", "value": "Texto"},
        "description": {"decision": "REJECTED", "value": "Texto"},
    }
    authorized = [{"id": "a"}]
    result = rows(
        proposal_completion(proposed, {}, decisions, authorized, current=True)
    )
    assert result["title"]["state"] == "ACCEPTED_FOR_INTERNAL_DRAFT"
    assert result["description"]["state"] == "REJECTED"
    assert result["short_title"]["state"] == "PROPOSED_REVIEW_REQUIRED"
    stale = rows(proposal_completion(proposed, {}, decisions, [], current=False))
    assert {stale[key]["state"] for key in proposed} == {"STALE"}
    applied = rows(
        proposal_completion(
            proposed,
            {"title": "Texto"},
            decisions,
            authorized,
            current=False,
            applied=True,
        )
    )
    assert applied["title"]["state"] == "SAVED_IN_INTERNAL_DRAFT"
    assert applied["description"]["state"] == "REJECTED"
    assert applied["short_title"]["state"] == "PROPOSED_NOT_APPLIED"
    assert not any(row["current_evidence_supported"] for row in applied.values())


def test_missing_citation_never_counts_as_current_even_if_proposal_flag_is_current():
    result = rows(
        proposal_completion(
            {"title": {"value": "Texto", "evidence_ids": ["unknown"]}},
            {},
            {},
            [{"id": "other"}],
            current=True,
        )
    )
    assert result["title"]["state"] == "STALE"


def test_saved_proposal_reopens_with_complete_coverage_and_rejects_revoked_evidence(
    tmp_path,
    monkeypatch,
):
    engine = case(tmp_path, monkeypatch)
    with Session(engine) as db:
        _doc, user = install_fake_source(db)
        proposal = Proposals(db, user).generate(IDENT, 0)
        result = rows(proposal["completion"])
        assert result["title"]["state"] == "PROPOSED_REVIEW_REQUIRED"
        draft_id, revision = proposal["draft_id"], proposal["revision"]
    with Session(engine) as db:
        service = Proposals(db, user)
        reopened = service.latest(IDENT)
        assert reopened["draft_id"] == draft_id
        assert rows(reopened["completion"])["title"]["current_evidence_supported"]
        research = Research(db, user)
        dossier = research.dossier(IDENT)
        approved = next(f for f in dossier.facts if f["field"] == "product_name")
        research.review(
            IDENT,
            dossier.version,
            approved["id"],
            approved["version"],
            "REVOKED",
            "Revocación explícita del hecho SINTÉTICO de prueba.",
        )
        stale = service.latest(IDENT)
        assert stale["state"] == "STALE"
        assert rows(stale["completion"])["title"]["state"] == "STALE"
        with pytest.raises(ValueError, match="desactualizada"):
            service.review(
                IDENT,
                draft_id,
                revision,
                {
                    "title": {
                        "decision": "ACCEPTED",
                        "value": reopened["fields"]["title"]["value"],
                    },
                },
            )


def test_effective_media_state_is_serialized_for_exact_saved_asset(
    tmp_path, monkeypatch
):
    engine = case(tmp_path, monkeypatch)
    media = complete_fields()["media"][0]
    with Session(engine) as db:
        doc, user = install_fake_source(db)
        fields = {**blank_fields(), "media": [media]}
        EcommApiProductWorkspace(db).save(IDENT, fields, "DRAFT", 0)
        document_id = doc.id
        db.commit()
    with Session(engine) as db:
        research = Research(db, user)
        dossier = research.dossier(IDENT)
        report = research.serialize(dossier)["media_rights"]
        assert report[0]["state"] == "APPROVED_CURRENT"
        assert report[0]["document_hash"] == db.get(Document, document_id).digest
        assert report[0]["ecomm_id"] == IDENT
        doc = db.get(Document, document_id)
        doc.digest = "f" * 64
        stale = research.serialize(dossier)["media_rights"]
        assert stale[0]["state"] == "STALE"
        assert stale[0]["current"] is False
        assert "MEDIA_RIGHTS_REVIEW" in [h["action"] for h in dossier.history]


def test_video_permission_is_exact_revocable_and_never_shared_with_other_assets(
    tmp_path,
    monkeypatch,
):
    engine = case(tmp_path, monkeypatch)
    video = {
        "kind": "VIDEO",
        "url": "https://fabricante-prueba.invalid/video.mp4",
        "source_url": URL,
    }
    with Session(engine) as db:
        doc, user = install_fake_source(db)
        body = deepcopy(doc.body)
        quote = f"El titular autoriza el uso comercial de {video['url']} en KIKI."
        body["sections"]["texto/linea/9"] = quote
        raw = "\n".join(body["sections"].values()).encode()
        checksum = sha256(raw).hexdigest()
        body["original_base64"] = base64.b64encode(raw).decode()
        body["original"].update(size=len(raw), sha256=checksum)
        body["provenance"] = "local://sha256/" + checksum
        doc.body, doc.digest = body, digest(body)
        db.flush()
        research = Research(db, user)
        dossier = research.dossier(IDENT)
        # The original's hash changed when this fictional permission was
        # added. Its prior identity decision cannot approve the revised file.
        previous_version = dossier.version
        reviewed = research.review_document_identity(
            IDENT, dossier.version, doc.id, doc.version, "APPROVED",
            "Revisé explícitamente la identidad y presentación del original ficticio con el nuevo permiso de video.",
        )
        assert reviewed["version"] > previous_version
        dossier = research.dossier(IDENT)
        review_media_rights(
            research,
            IDENT,
            dossier.version,
            doc.id,
            doc.version,
            video["url"],
            "VIDEO",
            URL,
            "APPROVED",
            "OWNER_AUTHORIZATION",
            "texto/linea/9",
            quote,
            "Permiso ficticio del video revisado expresamente en prueba.",
        )
        dossier = research.dossier(IDENT)
        report = media_permission_report(
            research, dossier, [video, {**video, "url": video["url"] + "?other"}]
        )
        assert [row["state"] for row in report] == ["APPROVED_CURRENT", "NO_PERMISSION"]
        review_media_rights(
            research,
            IDENT,
            dossier.version,
            doc.id,
            doc.version,
            video["url"],
            "VIDEO",
            URL,
            "REVOKED",
            "OWNER_AUTHORIZATION",
            "texto/linea/9",
            quote,
            "Revocación explícita del permiso ficticio del video en prueba.",
        )
        assert (
            media_permission_report(research, research.dossier(IDENT), [video])[0][
                "state"
            ]
            == "REVOKED"
        )
