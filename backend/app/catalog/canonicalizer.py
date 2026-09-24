from collections import defaultdict
from dataclasses import dataclass, field
from typing import Hashable

from .models import EcommChannelRow, Product


@dataclass
class CanonicalizationReport:
    products: list[Product]
    raw_rows: int
    grouped_rows: int
    associated_rows: int
    conflicts: list[str] = field(default_factory=list)


class EcommCanonicalizer:
    """Collapse channel rows into products without using mutable display data."""

    canonical_fields = (
        "name",
        "brand",
        "list_price",
        "cost",
        "stock",
    )

    def canonicalize(self, rows: list[EcommChannelRow]) -> CanonicalizationReport:
        groups: dict[Hashable, list[EcommChannelRow]] = defaultdict(list)
        for row in rows:
            groups[self._key(row)].append(row)

        conflicts: list[str] = []
        products = [
            self._product(key, members, conflicts) for key, members in groups.items()
        ]
        self._identifier_conflicts(products, conflicts)
        associated = sum(
            bool(row.marketplace or row.marketplace_id or row.store or row.listing_id)
            for row in rows
        )
        return CanonicalizationReport(
            products=products,
            raw_rows=len(rows),
            grouped_rows=len(rows) - len(products),
            associated_rows=associated,
            conflicts=conflicts,
        )

    @staticmethod
    def _key(row: EcommChannelRow) -> tuple[str, ...]:
        if row.ecomm_id:
            return ("id", row.ecomm_id)
        # Rows reaching this point have at least one accepted identifier. Keeping
        # variant and product namespaces separate avoids an unsafe accidental merge.
        if row.sku_variant:
            return ("variant", row.sku_variant)
        if row.sku_product:
            return ("product", row.sku_product)
        return ("ean", row.ean or "")

    def _product(
        self,
        key: Hashable,
        rows: list[EcommChannelRow],
        conflicts: list[str],
    ) -> Product:
        selected = {}
        for field_name in self.canonical_fields:
            values = []
            for row in rows:
                value = getattr(row, field_name)
                if value is not None and value not in values:
                    values.append(value)
            selected[field_name] = values[0] if values else None
            if len(values) > 1:
                conflicts.append(
                    f"{self._key_label(key)}: valores diferentes para {field_name} "
                    f"({', '.join(map(str, values))})."
                )

        first = rows[0]
        sku_products = self._distinct(row.sku_product for row in rows)
        sku_variants = self._distinct(row.sku_variant for row in rows)
        eans = self._distinct(row.ean for row in rows)
        sku_product = sku_products[0] if sku_products else None
        sku_variant = sku_variants[0] if sku_variants else None
        sku_effective = sku_variant or sku_product
        sku_aliases = self._distinct([*sku_variants, *sku_products])
        self._alias_conflict(key, "SKU de variante", sku_variants, conflicts)
        self._alias_conflict(key, "SKU de producto", sku_products, conflicts)
        self._alias_conflict(key, "EAN", eans, conflicts)
        return Product(
            ecomm_id=first.ecomm_id,
            sku=sku_effective,
            sku_product=sku_product,
            sku_variant=sku_variant,
            sku_effective=sku_effective,
            sku_source="sku_variant"
            if sku_variant
            else "sku_product"
            if sku_product
            else None,
            sku_aliases=sku_aliases,
            ean=eans[0] if eans else None,
            ean_aliases=eans,
            name=selected["name"],
            brand=selected["brand"],
            # List price is product-level. Marketplace prices remain only on rows.
            price=selected["list_price"],
            list_price=selected["list_price"],
            cost=selected["cost"],
            stock=selected["stock"],
            ecomm_rows=rows,
        )

    @staticmethod
    def _key_label(key: Hashable) -> str:
        return "/".join(str(part) for part in key)

    @staticmethod
    def _identifier_conflicts(products: list[Product], conflicts: list[str]) -> None:
        for field_name, aliases_name in (
            ("SKU", "sku_aliases"),
            ("EAN", "ean_aliases"),
        ):
            owners: dict[str, list[str]] = defaultdict(list)
            for product in products:
                for value in getattr(product, aliases_name):
                    owners[value].append(product.ecomm_id or "sin ID interno")
            for value, ecomm_ids in owners.items():
                if len(ecomm_ids) > 1:
                    conflicts.append(
                        f"{field_name} {value}: compartido por productos "
                        f"canónicos distintos ({', '.join(ecomm_ids)})."
                    )

    @staticmethod
    def _distinct(values) -> list[str]:
        return list(dict.fromkeys(value for value in values if value))

    @classmethod
    def _alias_conflict(
        cls, key: Hashable, label: str, aliases: list[str], conflicts: list[str]
    ) -> None:
        if len(aliases) > 1:
            conflicts.append(
                f"{cls._key_label(key)}: múltiples {label} asociados "
                f"({', '.join(aliases)})."
            )
