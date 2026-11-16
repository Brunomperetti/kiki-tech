"""Documental pilot: Ecomm export GTIN is search identity, never manufacturer proof.

All records are synthetic. No network, provider, database migration or production writes.
"""
from types import SimpleNamespace

import pytest

from app.services.documental.research import Research, identity_digest


CODE = "8410771100656"
ID = "6708522"
SKU = "5221"


def row(*, code=CODE, status="VALID_UNIQUE", combo=False, sku=SKU):
    return {
        "ecomm_id": ID,
        "sku": sku,
        "gtin": code,
        "status": status,
        "is_combo": combo,
    }


def stage(*, sku=SKU, combo=False):
    return [{
        "items": [{
            "is_combo": combo,
            "description": "Torta de turrón para ensayo sintético",
            "variants": [{"id": ID, "sku": sku, "is_combo": combo, "gtin": None, "barcode": None}],
        }]
    }]


def source(*, gtin=None, combo=False):
    return {
        "identity_blockers": [],
        "product_name": "Torta de turrón para ensayo sintético",
        "sku": SKU,
        "variant_description": "150 g",
        "is_combo": combo,
        "parent_is_combo": combo,
        "gtin": gtin,
        "barcode": None,
        "gtin_raw": None,
        "brand": None,
        "manufacturer": None,
    }


def research(*, excel=None, pages=None, record=None):
    s = Research.__new__(Research)
    captured = pages if pages is not None else stage()
    snapshot = record if record is not None else {
        "version": 1, "variants": 1, "rows": [excel or row()],
    }
    s.db = SimpleNamespace(scalar=lambda _: SimpleNamespace(payload=[snapshot]))
    s.workspace_type = lambda _: SimpleNamespace(_source_pages=lambda: captured)
    s.source_record = lambda _: source()
    s.edit_record = lambda _: None
    return s


def test_unique_non_combo_excel_gtin_is_attributed_reference_only():
    ref = research().reference(ID)
    assert ref["ecomm_id"] == ID and ref["sku"] == SKU
    assert ref["ean"] == CODE
    assert "Excel" in ref["provenance"]["ean"]
    assert "no verificado" in ref["provenance"]["ean"]
    assert not Research.identity_issues(ref, {
        "identity": {
            "name": ref["name"], "presentation": ref["presentation"],
            "ean": CODE, "is_combo": False,
        },
        "associated_ecomm_id": ID,
    })
    wrong = Research.identity_issues(ref, {
        "identity": {"name": ref["name"], "presentation": ref["presentation"],
                     "ean": "7798180790097", "is_combo": False},
        "associated_ecomm_id": ID,
    })
    assert any("EAN incompatible" in problem for problem in wrong)


@pytest.mark.parametrize("modified", [
    {"excel": row(status="VALID_REPEATED")},
    {"excel": row(status="PACK_REVIEW", combo=True)},
    {"excel": row(code="3", status="INVALID")},
    {"excel": row(sku="WRONG")},
    {"pages": stage(sku="WRONG")},
    {"pages": stage(combo=True)},
    {"record": {"version": 1, "variants": 2, "rows": [row()]}},
    {"record": {"version": 1, "variants": 1, "rows": [row(), row()]}},
])
def test_no_export_gtin_when_evidence_is_ineligible_or_stale(modified):
    ref = research(**modified).reference(ID)
    assert ref["ean"] is None
    assert "Captura API" in ref["provenance"]["ean"]


def test_canonical_api_gtin_takes_priority_and_avoids_export_query():
    candidate = research()
    candidate.source_record = lambda _: source(gtin=CODE)
    candidate.db = SimpleNamespace(scalar=lambda _: pytest.fail("No extra export lookup"))
    ref = candidate.reference(ID)
    assert ref["ean"] == CODE
    assert "Captura API" in ref["provenance"]["ean"]


def test_suspended_export_changes_identity_fingerprint_and_requires_new_evidence():
    with_excel = research().reference(ID)
    without = research(excel=row(sku="WRONG")).reference(ID)
    assert with_excel["ean"] == CODE and without["ean"] is None
    assert identity_digest(with_excel) != identity_digest(without)
    # Attribution alone is display metadata, not a factual identity field.
    copy = {**with_excel, "provenance": {"ean": "Otra frase de procedencia"}}
    assert identity_digest(with_excel) == identity_digest(copy)
