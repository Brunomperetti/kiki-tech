"""Reconciled manufacturer names are explicit reviewed facts, never auto-matches.

Offline tests exercise the production Research methods with a realistic Ecomm
identity and a synthetic source document. No provider, migration, or AI calls.
"""
from copy import deepcopy
from types import MethodType, SimpleNamespace

import pytest

from app.services.documental.research import Research, identity_digest


ID = "7518949"
RAW = "Mix Semillas P/ Ensaladas Sopas Natural Seed X 250gr"
LOOKUP = "7798180790097"


def setup_case(*, ean=None, sale=None, state="REVIEWED", combo=False):
    identity = {
        "ecomm_id": ID,
        "sku": "9995",
        "name": RAW,
        "presentation": RAW,
        "is_combo": combo,
        "lookup_gtin": LOOKUP,
        "ean": None,
        "editorial_presentation": None,
    }
    dossier = SimpleNamespace(
        ecomm_id=ID,
        version=0,
        identity=identity,
        identity_digest=identity_digest(identity),
        facts=[],
        history=[],
    )
    document = SimpleNamespace(
        id="local-" + "1" * 32,
        version=1,
        digest="a" * 64,
        body={
            "associated_ecomm_id": ID,
            "identity": {
                "name": "Mix Ensaladas y Sopas",
                "presentation": "250 g",
                "ean": ean,
                "is_combo": sale,
            },
            "source": {"review_state": state},
            "parse_status": "TEXT_EXTRACTED",
            "parser_blockers": [],
            "sections": {
                "texto/linea/1": "Nombre: Mix Ensaladas y Sopas",
                "texto/linea/2": "Presentación: 250 g",
            },
            "identity_evidence": {
                "name": {
                    "value": "Mix Ensaladas y Sopas",
                    "location": "texto/linea/1",
                    "quote": "Nombre: Mix Ensaladas y Sopas",
                },
                "presentation": {
                    "value": "250 g",
                    "location": "texto/linea/2",
                    "quote": "Presentación: 250 g",
                },
            },
        },
    )
    research = Research.__new__(Research)
    research.actor = "operador de prueba"
    research.dossier = lambda _: dossier
    research._document = lambda _: document
    research.additional_blockers = lambda *_: []
    research.refresh = lambda *_: None
    research.serialize = lambda _: {"status": "stored", "version": dossier.version}

    def commit(self, item, facts, action, detail=None):
        item.version += 1
        item.history = [*item.history, {
            "action": action, "detail": deepcopy(detail), "version": item.version,
        }]
    research.commit_change = MethodType(commit, research)
    return research, dossier, document


def approve(service, case, doc):
    return service.review_document_identity(
        ID, case.version, doc.id, doc.version, "APPROVED",
        "Comparé etiqueta original y variante de este SKU y presentación.",
    )


def test_reviewed_alias_clears_only_name_and_presentation_for_exact_document():
    service, case, doc = setup_case()
    mismatches = service.identity_blockers(case, doc)
    assert any(x.startswith("Nombre incompatible") for x in mismatches)
    assert any(x.startswith("Presentación incompatible") for x in mismatches)
    assert approve(service, case, doc) == {"status": "stored", "version": 1}
    assert service.identity_blockers(case, doc) == []
    record = case.history[-1]["detail"]
    assert record["document_hash"] == doc.digest
    assert record["source_presentation"] == RAW
    assert record["document_presentation"] == "250 g"
    assert record["ecomm_id"] == ID and record["reviewer"]
    assert record["decision"] == "APPROVED"


def test_stale_identity_and_new_document_must_be_reviewed_again():
    service, case, doc = setup_case()
    approve(service, case, doc)
    other = deepcopy(doc)
    other.id = "local-" + "2" * 32
    assert service.identity_blockers(case, other)
    doc.version += 1
    assert service.identity_blockers(case, doc)
    doc.version -= 1
    doc.digest = "b" * 64
    assert service.identity_blockers(case, doc)
    doc.digest = "a" * 64
    case.identity["sku"] = "9996"
    case.identity_digest = identity_digest(case.identity)
    assert service.identity_blockers(case, doc)


def test_revocation_resumes_identity_blockers_and_requires_new_version():
    service, case, doc = setup_case()
    approve(service, case, doc)
    with pytest.raises(ValueError, match="otra sesión"):
        service.review_document_identity(
            ID, 0, doc.id, doc.version, "REVOKED",
            "Revisé de nuevo la fuente y no corresponde a la misma presentación.",
        )
    result = service.review_document_identity(
        ID, 1, doc.id, doc.version, "REVOKED",
        "Revisé de nuevo la fuente y no corresponde a la misma presentación.",
    )
    assert result["version"] == 2
    assert case.history[-1]["detail"]["decision"] == "REVOKED"
    assert service.identity_blockers(case, doc)
    with pytest.raises(ValueError, match="no hay una conciliación"):
        service.review_document_identity(
            ID, 2, doc.id, doc.version, "REVOKED",
            "La equivalencia anterior ya había sido revocada con motivo.",
        )


@pytest.mark.parametrize("changes", [
    {"ean": "8410771100656"},
    {"sale": True},
    {"state": "PENDING"},
    {"combo": True},
])
def test_conflicting_ean_pack_or_unreviewed_source_cannot_be_reconciled(changes):
    service, case, doc = setup_case(**changes)
    with pytest.raises(ValueError):
        approve(service, case, doc)
    assert case.history == []
    assert case.version == 0


def test_incomplete_document_identity_and_cross_variant_rejected():
    service, case, doc = setup_case()
    doc.body["identity"]["name"] = ""
    with pytest.raises(ValueError, match="explícitamente nombre"):
        approve(service, case, doc)
    doc.body["identity"]["name"] = "Mix Ensaladas y Sopas"
    doc.body["associated_ecomm_id"] = "7777"
    with pytest.raises(ValueError, match="otra variante|solo puede"):
        approve(service, case, doc)
    assert case.history == []


def test_review_metadata_cannot_approve_commercial_claim_or_gtin():
    service, case, doc = setup_case()
    approve(service, case, doc)
    assert case.history[-1]["action"] == "DOCUMENT_IDENTITY_REVIEW"
    # No facts or fields are introduced by the identity decision.
    assert case.facts == []
    assert case.identity["ean"] is None
    assert case.identity["lookup_gtin"] == LOOKUP
    assert not any("CERTIFIC" in str(event) for event in case.history)



@pytest.mark.parametrize("tamper", ["missing_quote", "wrong_size", "missing_section"])
def test_unquoted_or_tampered_source_identity_cannot_be_reconciled(tamper):
    service, case, doc = setup_case()
    if tamper == "missing_quote":
        doc.body["identity_evidence"]["name"]["quote"] = "Nombre no existe"
    elif tamper == "wrong_size":
        doc.body["identity_evidence"]["presentation"]["value"] = "500 g"
    else:
        doc.body["sections"].pop("texto/linea/1")
    with pytest.raises(ValueError, match="citas literales"):
        approve(service, case, doc)
    assert case.history == []
