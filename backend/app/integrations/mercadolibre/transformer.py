from decimal import Decimal

from ...catalog.models import Channel, ChannelListing


def _attribute(attributes: list[dict], names: set[str]) -> str | None:
    for attribute in attributes or []:
        if str(attribute.get("id", "")).upper() in names:
            value = attribute.get("value_name") or attribute.get("value_id")
            if value is not None:
                return str(value)
    return None


def transform_item(item: dict) -> list[ChannelListing]:
    attributes = item.get("attributes") or []
    product_sku = _attribute(attributes, {"SELLER_SKU", "SKU"}) or item.get(
        "seller_custom_field"
    )
    product_ean = _attribute(attributes, {"GTIN", "EAN", "EAN13"})
    common = {
        "channel": Channel.MERCADOLIBRE_API,
        "title": item.get("title"),
        "status": item.get("status"),
        "url": item.get("permalink"),
    }
    variations = item.get("variations") or []
    if not variations:
        return [
            ChannelListing(
                **common,
                external_id=str(item.get("id")),
                sku=product_sku,
                sku_product=product_sku,
                sku_effective=product_sku,
                sku_source="product" if product_sku else None,
                ean=product_ean,
                price=Decimal(str(item["price"]))
                if item.get("price") is not None
                else None,
            )
        ]
    result = []
    for variation in variations:
        variant_sku = _attribute(
            variation.get("attributes") or [], {"SELLER_SKU", "SKU"}
        ) or variation.get("seller_custom_field")
        variant_ean = _attribute(
            variation.get("attributes") or [], {"GTIN", "EAN", "EAN13"}
        )
        effective = variant_sku or product_sku
        result.append(
            ChannelListing(
                **common,
                external_id=f"{item.get('id')}#{variation.get('id')}",
                sku=effective,
                sku_product=product_sku,
                variant_sku=variant_sku,
                sku_effective=effective,
                sku_source="variant"
                if variant_sku
                else ("product" if product_sku else None),
                ean=variant_ean or product_ean,
                price=Decimal(str(variation.get("price", item.get("price"))))
                if variation.get("price", item.get("price")) is not None
                else None,
            )
        )
    return result
