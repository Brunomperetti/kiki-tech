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
    assert ref["ean"] is None  # Never promote a spreadsheet lookup to official API EAN.
    assert ref["lookup_gtin"] == CODE
    assert "Excel" in ref["provenance"]["lookup_gtin"]
    assert "no GTIN certificado" in ref["provenance"]["lookup_gtin"]
    assert not Research.identity_issues(ref, {
        "identity": {
            "name": ref["name"], "presentation": ref["presentation"],
            "ean": CODE, "is_combo": False,
        },
        "associated_ecomm_id": ID,
    })
    # An authentic manufacturer page is not required to publish an EAN,
    # provided product name, presentation and unit type match.
    assert not Research.identity_issues(ref, {
        "identity": {
            "name": ref["name"], "presentation": ref["presentation"],
            "ean": None, "is_combo": False,
        },
        "associated_ecomm_id": ID,
    })
    wrong = Research.identity_issues(ref, {
        "identity": {"name": ref["name"], "presentation": ref["presentation"],
                     "ean": "7798180790097", "is_combo": False},
        "associated_ecomm_id": ID,
    })
    assert any("pista GTIN" in problem for problem in wrong)


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
    assert ref["lookup_gtin"] is None
    assert "Sin código externo" in ref["provenance"]["lookup_gtin"]


def test_export_index_is_loaded_once_per_guarded_research_request():
    candidate = research()
    calls = []
    old_scalar = candidate.db.scalar

    def counted_scalar(statement):
        calls.append(statement)
        return old_scalar(statement)

    candidate.db = SimpleNamespace(scalar=counted_scalar)
    assert candidate.reference(ID)["lookup_gtin"] == CODE
    assert candidate.reference(ID)["lookup_gtin"] == CODE
    # Multiple references to the same snapshot share one validated index.
    assert len(calls) == 1
    # A new Research request does not inherit the previous map.
    assert research(excel=row(status="VALID_REPEATED")).reference(ID)["lookup_gtin"] is None


def test_repeated_gtin_is_rejected_even_if_export_status_says_unique():
    other_id, other_sku = "6708523", "5222"
    captured = stage()
    captured[0]["items"][0]["variants"].append({
        "id": other_id, "sku": other_sku, "is_combo": False,
        "gtin": None, "barcode": None,
    })
    record = {"version": 1, "variants": 2, "rows": [
        row(), {**row(), "ecomm_id": other_id, "sku": other_sku},
    ]}
    ref = research(pages=captured, record=record).reference(ID)
    assert ref["lookup_gtin"] is None
    assert ref["ean"] is None


def test_canonical_api_gtin_takes_priority_and_avoids_export_query():
    candidate = research()
    candidate.source_record = lambda _: source(gtin=CODE)
    candidate.db = SimpleNamespace(scalar=lambda _: pytest.fail("No extra export lookup"))
    ref = candidate.reference(ID)
    assert ref["ean"] == CODE
    assert ref["lookup_gtin"] is None
    assert "Captura API" in ref["provenance"]["ean"]


def test_suspended_export_changes_identity_fingerprint_and_requires_new_evidence():
    with_excel = research().reference(ID)
    without = research(excel=row(sku="WRONG")).reference(ID)
    assert with_excel["lookup_gtin"] == CODE and without["lookup_gtin"] is None
    assert identity_digest(with_excel) != identity_digest(without)
    # Attribution alone is display metadata, not a factual identity field.
    copy = {**with_excel, "provenance": {"ean": "Otra frase de procedencia"}}
    assert identity_digest(with_excel) == identity_digest(copy)



def test_official_product_page_without_unit_marker_can_be_reviewed_by_exact_identity():
    """Real manufacturers often omit 'tipo de venta: unidad' entirely."""
    ref = research().reference(ID)
    document = {
        "identity": {
            "name": ref["name"], "presentation": ref["presentation"],
            "ean": None, "is_combo": None,
        },
        "associated_ecomm_id": ID,
    }
    assert Research.identity_issues(ref, document) == []
    # A changed presentation, foreign Ecomm ID or incompatible printed GTIN
    # still blocks approval; sale-type omission does not override identity.
    changed = {**document, "identity": {**document["identity"], "presentation": "1 kg"}}
    assert any("Presentación" in issue for issue in Research.identity_issues(ref, changed))
    alien = {**document, "associated_ecomm_id": "999999"}
    assert any("otro Ecomm ID" in issue for issue in Research.identity_issues(ref, alien))
    ean_conflict = {**document, "identity": {**document["identity"], "ean": "7798180790097"}}
    assert any("pista GTIN" in issue for issue in Research.identity_issues(ref, ean_conflict))


def test_pack_requires_explicit_sale_type_even_when_name_and_presentation_match():
    ref = research().reference(ID)
    ref["is_combo"] = True
    ref["parent_is_combo"] = True
    document = {
        "identity": {
            "name": ref["name"], "presentation": ref["presentation"],
            "ean": None, "is_combo": None,
        },
        "associated_ecomm_id": ID,
    }
    missing_type = Research.identity_issues(ref, document)
    assert any("Pack/kit" in issue for issue in missing_type)
    unit_type = {**document, "identity": {**document["identity"], "is_combo": False}}
    assert any("incompatible" in issue for issue in Research.identity_issues(ref, unit_type))
    explicit_pack = {**document, "identity": {**document["identity"], "is_combo": True}}
    assert Research.identity_issues(ref, explicit_pack) == []
