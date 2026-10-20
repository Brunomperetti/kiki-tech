import pytest

from app.services.sku_family_service import compare_family_skus, diagnose_duplicate_group


@pytest.mark.parametrize(
    "left,right,expected",
    [
        ("5028", "5028", "SAME_SKU"),
        ("SKU-A", "SKU-A", "SAME_SKU"),
        ("5028", "5028000", "PREFIX_4"),
        ("5028", "5028999", "PREFIX_4"),
        ("5028000", "5028999", "PREFIX_4"),
        ("5028", "5029", "PREFIX_3"),
        ("50100", "50999", "PREFIX_2_SPECIAL"),
        ("50100", "50888", "PREFIX_2_SPECIAL"),
        ("50100", "50333", "PREFIX_2_SPECIAL"),
        ("5028000", "7799999", "NO_RULE"),
        ("50345", "51999", "NO_RULE"),
        ("50999", "51000", "NO_RULE"),
        ("5028-A", "5028", "NOT_NUMERIC"),
        ("", "5028", "NOT_NUMERIC"),
    ],
)
def test_sku_family_pattern_examples(left, right, expected):
    output = compare_family_skus(left, right)
    assert output["rule"] == expected
    assert output["related"] == (expected not in {"NO_RULE", "NOT_NUMERIC"})


def test_three_confirmed_family_examples_do_not_authorize_variant_decision():
    hint = diagnose_duplicate_group(
        [{"sku": "5028"}, {"sku": "5028000"}, {"sku": "5028999"}]
    )
    assert hint["status"] == "FAMILY_CANDIDATE"
    assert hint["comparisons"] == 3
    assert hint["matches"] == 3
    assert "NO variantes" in hint["policy"]


def test_bad_pair_in_shared_alias_group_is_not_auto_cleared():
    hint = diagnose_duplicate_group(
        [{"sku": "5028"}, {"sku": "5028000"}, {"sku": "7799"}]
    )
    assert hint["status"] == "REVIEW_REQUIRED"
    assert hint["comparisons"] == 3
    assert hint["matches"] == 1


def test_same_sku_still_needs_duplication_review():
    hint = diagnose_duplicate_group([{"sku": "777"}, {"sku": "777"}])
    assert hint["status"] == "FAMILY_CANDIDATE"
    assert hint["pairs"][0]["rule"] == "SAME_SKU"
    assert "duplicados confirmados" in hint["policy"]
