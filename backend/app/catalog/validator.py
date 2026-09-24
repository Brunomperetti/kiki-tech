import re
from collections import Counter
from .models import Product, Severity, ValidationIssue


class ProductValidator:
    def validate(
        self, product: Product, sku_counts: Counter[str] | None = None
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        def add(field: str, severity: Severity, code: str, message: str) -> None:
            issues.append(
                ValidationIssue(
                    field=field, severity=severity, code=code, message=message
                )
            )

        if not product.sku:
            add("sku", Severity.ERROR, "SKU_MISSING", "El producto no tiene SKU.")
        elif not re.fullmatch(r"[A-Z0-9._/-]+", product.sku):
            add(
                "sku",
                Severity.ERROR,
                "SKU_INVALID",
                "El SKU contiene caracteres no válidos.",
            )
        elif sku_counts and any(
            sku_counts[sku] > 1 for sku in product.sku_aliases or [product.sku]
        ):
            add(
                "sku",
                Severity.ERROR,
                "SKU_DUPLICATE",
                "El SKU está duplicado en Ecomm-App.",
            )
        if not product.ean:
            add(
                "ean", Severity.WARNING, "EAN_MISSING", "El producto no tiene EAN/GTIN."
            )
        elif not (product.ean.isdigit() and len(product.ean) in {8, 12, 13, 14}):
            add(
                "ean",
                Severity.ERROR,
                "EAN_INVALID",
                "El EAN/GTIN debe tener 8, 12, 13 o 14 dígitos.",
            )
        if not product.name:
            add("name", Severity.ERROR, "NAME_MISSING", "El producto no tiene nombre.")
        if product.price is None or product.price <= 0:
            add(
                "price",
                Severity.ERROR,
                "PRICE_INVALID",
                "El precio debe ser mayor que cero.",
            )
        if product.stock is None:
            add(
                "stock",
                Severity.WARNING,
                "STOCK_MISSING",
                "El producto no tiene stock informado.",
            )
        elif product.stock < 0:
            add(
                "stock",
                Severity.ERROR,
                "STOCK_INVALID",
                "El stock no puede ser negativo.",
            )
        if not product.brand:
            add("brand", Severity.INFO, "BRAND_MISSING", "La marca no está informada.")
        return issues
