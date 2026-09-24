from app.catalog.models import (
    ChannelListing,
    MatchMethod,
    Product,
    ReconciliationStatus,
)
from app.catalog.reconciler import CatalogReconciler


def product(**kw):
    return Product(
        sku="A1",
        ean="7791234567890",
        name="Café premium 500g",
        brand="Kiki",
        price=10,
        stock=2,
        **kw,
    )


def test_match_by_sku():
    r = CatalogReconciler().reconcile(
        [product()], [ChannelListing(external_id="ML1", sku="A1", title="Otro")]
    )[0]
    assert (r.status, r.match_method) == (
        ReconciliationStatus.ALREADY_PUBLISHED,
        MatchMethod.SKU,
    )
    assert r.matched_listing_count == 1
    assert r.matched_listing_ids == ["ML1"]
    assert r.multiple_ml_listings is False


def test_match_by_ean():
    r = CatalogReconciler().reconcile(
        [product()], [ChannelListing(external_id="ML1", sku="X", ean="7791234567890")]
    )[0]
    assert r.match_method == MatchMethod.EAN


def test_no_match_is_candidate():
    assert (
        CatalogReconciler().reconcile([product()], [])[0].status
        == ReconciliationStatus.CANDIDATE_TO_PUBLISH
    )


def test_text_match_requires_review():
    r = CatalogReconciler().reconcile(
        [product()], [ChannelListing(external_id="ML1", title="Cafe premium 500g")]
    )[0]
    assert r.status == ReconciliationStatus.REVIEW_REQUIRED


def test_text_match_still_works_with_large_listing_set():
    listings = [
        ChannelListing(external_id=f"NOISE-{i}", title=f"Producto distinto {i}")
        for i in range(1000)
    ]
    listings.append(ChannelListing(external_id="ML1", title="Cafe premium 500g"))
    r = CatalogReconciler().reconcile([product()], listings)[0]
    assert r.status == ReconciliationStatus.REVIEW_REQUIRED
    assert r.match_method == MatchMethod.TITLE


def test_multiple_sku_matches_are_already_published():
    listings = [ChannelListing(external_id=str(i), sku="A1") for i in range(2)]
    result = CatalogReconciler().reconcile([product()], listings)[0]
    assert result.status == ReconciliationStatus.ALREADY_PUBLISHED
    assert result.matched_listing_count == 2
    assert result.matched_listing_ids == ["0", "1"]
    assert result.multiple_ml_listings is True


def test_active_and_paused_sku_matches_are_already_published():
    listings = [
        ChannelListing(external_id="ML1", sku="A1", status="active"),
        ChannelListing(external_id="ML2", sku="A1", status="paused"),
    ]
    result = CatalogReconciler().reconcile([product()], listings)[0]
    assert result.status == ReconciliationStatus.ALREADY_PUBLISHED
    assert result.multiple_ml_listings is True
    assert result.listing == listings[0]


def test_duplicate_product_sku():
    results = CatalogReconciler().reconcile(
        [product(ecomm_id="1"), product(ecomm_id="2")], []
    )
    assert all(x.status == ReconciliationStatus.POSSIBLE_DUPLICATE for x in results)


def test_incomplete_data():
    p = Product(sku="A1", ean="7791234567890", name=None, price=None, stock=1)
    assert (
        CatalogReconciler().reconcile([p], [])[0].status
        == ReconciliationStatus.INCOMPLETE_DATA
    )


def test_unmatched_listing_is_reported():
    result = CatalogReconciler().reconcile([], [ChannelListing(external_id="ML1")])[0]
    assert result.status == ReconciliationStatus.UNMATCHED_ML_LISTING


def test_ml_matches_an_alternative_product_sku():
    product_with_alias = product(sku_aliases=["A1", "OLD-A1"])
    result = CatalogReconciler().reconcile(
        [product_with_alias], [ChannelListing(external_id="ML1", sku="OLD-A1")]
    )[0]
    assert result.status == ReconciliationStatus.ALREADY_PUBLISHED
    assert result.matched_identifier == "OLD-A1"


def test_different_aliases_matching_different_listings_require_review():
    product_with_alias = product(sku_aliases=["A1", "OLD-A1"])
    listings = [
        ChannelListing(external_id="ML1", sku="A1"),
        ChannelListing(external_id="ML2", sku="OLD-A1"),
    ]
    result = CatalogReconciler().reconcile([product_with_alias], listings)[0]
    assert result.status == ReconciliationStatus.REVIEW_REQUIRED
    assert "aliases" in result.reason


def test_aliases_matching_same_listings_are_not_ambiguous():
    product_with_alias = product(sku_aliases=["A1", "OLD-A1"])
    listing = ChannelListing(external_id="ML1", sku="A1")
    matcher_result = CatalogReconciler().reconcile([product_with_alias], [listing])[0]
    assert matcher_result.status == ReconciliationStatus.ALREADY_PUBLISHED
