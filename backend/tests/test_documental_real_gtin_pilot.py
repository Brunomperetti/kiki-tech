"""Documental identity is Ecomm-App API only, without archived XLSX fallback.

All test records are synthetic. No network, provider or production writes.
"""
from types import SimpleNamespace

import pytest

from app.services.documental.research import Research, identity_digest


CODE = "8410771100656"
ID = "6708522"
SKU = "5221"


def source(*, gtin=None, combo=False):
    return {
        "identity_blockers": [],
        "product_name": "Torta de turrón para ensayo sintético",
        "sku": SKU,
        "variant_description": "150 g",
        "is_combo": combo,
        "parent_is_combo": combo,
        "gtin": gtin,
        "barcode": gtin,
        "gtin_raw": None,
        "brand": None,
        "manufacturer": None,
    }


def research(*, api_gtin=None):
    service = Research.__new__(Research)
    service.db = SimpleNamespace(
        scalar=lambda _: pytest.fail("No se permite acceder a un Excel histórico")
    )
    service.source_record = lambda _: source(gtin=api_gtin)
    service.edit_record = lambda _: None
    return service


def document(ref, *, code=None, combo=None, ident=ID):
    return {
        "identity": {
            "name": ref["name"], "presentation": ref["presentation"],
            "ean": code, "is_combo": combo,
        },
        "associated_ecomm_id": ident,
    }


def test_no_api_code_never_requests_or_inherits_ecomm_excel():
    reference = research().reference(ID)
    assert reference["ecomm_id"] == ID and reference["sku"] == SKU
    assert reference["ean"] is None
    assert reference["lookup_gtin"] is None
    assert "exclusivamente por API" in reference["provenance"]["lookup_gtin"]
    assert Research.identity_issues(reference, document(reference)) == []


def test_api_barcode_is_canonical_and_mismatch_is_blocked():
    reference = research(api_gtin=CODE).reference(ID)
    assert reference["ean"] == CODE
    assert reference["lookup_gtin"] is None
    assert "Captura API" in reference["provenance"]["ean"]
    # Manufacturer often omits barcode; absence is not a contradiction.
    assert Research.identity_issues(reference, document(reference)) == []
    assert Research.identity_issues(reference, document(reference, code=CODE)) == []
    different = Research.identity_issues(
        reference, document(reference, code="7798180790097")
    )
    assert any(problem.startswith("EAN incompatible") for problem in different)


def test_api_barcode_change_invalidates_identity_fingerprint():
    without = research().reference(ID)
    with_code = research(api_gtin=CODE).reference(ID)
    assert identity_digest(without) != identity_digest(with_code)
    # Changing display-only provenance has no effect on identity.
    copy = {**with_code, "provenance": {"ean": "Cualquier frase"}}
    assert identity_digest(with_code) == identity_digest(copy)


def test_unknown_api_barcode_does_not_certify_manufacturer_code():
    reference = research().reference(ID)
    # The document can record a printed code as unapproved evidence; it must
    # not be silently copied into reference['ean'] or reference['lookup_gtin'].
    assert Research.identity_issues(
        reference, document(reference, code=CODE)
    ) == []
    assert reference["ean"] is None and reference["lookup_gtin"] is None


def test_document_identity_and_pack_still_block_conflicts():
    reference = research(api_gtin=CODE).reference(ID)
    alien = Research.identity_issues(
        reference, document(reference, ident="9999999")
    )
    assert any("otro Ecomm ID" in x for x in alien)
    changed = document(reference)
    changed["identity"]["presentation"] = "500 g"
    assert any("Presentación" in x for x in Research.identity_issues(reference, changed))
    reference["is_combo"] = True
    reference["parent_is_combo"] = True
    assert any("Pack/kit" in x for x in Research.identity_issues(
        reference, document(reference)
    ))
    assert any("incompatible" in x for x in Research.identity_issues(
        reference, document(reference, combo=False)
    ))
    assert Research.identity_issues(
        reference, document(reference, combo=True)
    ) == []
