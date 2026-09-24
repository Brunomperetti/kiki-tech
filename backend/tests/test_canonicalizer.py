from decimal import Decimal

from app.catalog.canonicalizer import EcommCanonicalizer
from app.catalog.models import EcommChannelRow
from app.catalog.reconciler import CatalogReconciler
from app.catalog.models import ReconciliationStatus


def row(**overrides):
    values = {
        "ecomm_id": "10",
        "sku_product": "001",
        "sku_effective": "001",
        "name": "Café",
        "brand": "KIKI",
        "list_price": Decimal("120"),
        "cost": Decimal("50"),
        "stock": Decimal("2"),
    }
    values.update(overrides)
    return EcommChannelRow(**values)


def test_channel_rows_of_same_product_become_one_canonical_product():
    rows = [
        row(marketplace="Mercado Libre", marketplace_price=Decimal("130")),
        row(marketplace="Tienda Nube", marketplace_price=Decimal("125")),
        row(marketplace="Web", marketplace_price=Decimal("120")),
    ]

    report = EcommCanonicalizer().canonicalize(rows)

    assert len(report.products) == 1
    assert report.grouped_rows == 2
    assert report.associated_rows == 3
    assert report.products[0].price == Decimal("120")
    assert report.products[0].list_price == Decimal("120")
    assert [item.marketplace_price for item in report.products[0].ecomm_rows] == [
        Decimal("130"),
        Decimal("125"),
        Decimal("120"),
    ]
    result = CatalogReconciler().reconcile(report.products, [])[0]
    assert result.status == ReconciliationStatus.CANDIDATE_TO_PUBLISH


def test_different_internal_ids_with_same_sku_are_real_duplicates():
    canonical = EcommCanonicalizer().canonicalize(
        [row(ecomm_id="10"), row(ecomm_id="20")]
    )

    assert len(canonical.products) == 2
    assert any("SKU 001" in conflict for conflict in canonical.conflicts)
    results = CatalogReconciler().reconcile(canonical.products, [])
    assert all(
        item.status == ReconciliationStatus.POSSIBLE_DUPLICATE for item in results
    )


def test_canonical_conflicts_are_reported_without_losing_raw_values():
    canonical = EcommCanonicalizer().canonicalize(
        [row(stock=Decimal("2")), row(stock=Decimal("3"))]
    )

    assert len(canonical.products) == 1
    assert canonical.products[0].stock == Decimal("2")
    assert len(canonical.products[0].ecomm_rows) == 2
    assert any("stock" in conflict for conflict in canonical.conflicts)
