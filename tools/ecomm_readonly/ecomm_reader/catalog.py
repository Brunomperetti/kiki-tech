"""Strict data.items[].variants[].id decoding; no sources or identifiers invented."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
import math
import re
import unicodedata
from .policy import BARCODE, PAGE_SIZE
from .safety import Code, Failure


def normalized(value):
    return " ".join(
        unicodedata.normalize("NFKD", value.replace("×", "x"))
        .encode("ascii", "ignore")
        .decode()
        .casefold()
        .split()
    )


def variant_id(value):
    # Conservative pilot format; another vendor format requires explicit review.
    if type(value) is int:
        value = str(value)
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,119}", value):
        raise Failure(Code.ID)
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Failure(Code.JSON)
        result[key] = value
    return result


def invalid_constant(value):
    raise Failure(Code.JSON)


def decode(body, *, sensitive_value=None):
    try:
        result = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=invalid_constant,
        )
        count = 0

        def bound(value, depth=0):
            nonlocal count
            count += 1
            if depth > 32 or count > 20000:
                raise Failure(Code.LIMIT)
            if isinstance(value, dict):
                if len(value) > 100:
                    raise Failure(Code.LIMIT)
                for key, child in value.items():
                    if len(key) > 120:
                        raise Failure(Code.LIMIT)
                    if sensitive_value and sensitive_value in key:
                        raise Failure(Code.SECRET)
                    bound(child, depth + 1)
            elif isinstance(value, list):
                if len(value) > 2000:
                    raise Failure(Code.LIMIT)
                for child in value:
                    bound(child, depth + 1)
            elif (
                isinstance(value, str) and sensitive_value and sensitive_value in value
            ):
                raise Failure(Code.SECRET)
            elif isinstance(value, str) and (
                len(value) > 10000
                or any(ord(c) < 32 and c not in "\n\r\t" for c in value)
                or re.search("[\u202a-\u202e\u2066-\u2069]", value)
            ):
                raise Failure(Code.LIMIT)
            elif isinstance(value, float) and not math.isfinite(value):
                raise Failure(Code.JSON)

        bound(result)
        if (
            not isinstance(result, dict)
            or "error" in result
            or not isinstance(result.get("data"), dict)
        ):
            raise Failure(Code.JSON)
        data = result["data"]
        if not isinstance(data.get("items"), list) or len(data["items"]) > PAGE_SIZE:
            raise Failure(Code.JSON)
        return data
    except Failure:
        raise
    except Exception:
        raise Failure(Code.JSON) from None


@dataclass(frozen=True)
class Pagination:
    page: int
    total: int
    per_page: int
    total_pages: int


def pagination(data, expected_page, first=None):
    if "pagination" in data and "paginacion" in data:
        raise Failure(Code.PAGINATION)
    meta = data.get("pagination", data.get("paginacion"))
    if meta is None and expected_page == 1:
        return None  # no second request, no completeness/absence assertion
    if not isinstance(meta, dict):
        raise Failure(Code.PAGINATION)
    fields = [meta.get(k) for k in ("page", "total", "per_page", "total_pages")]
    if any(type(v) is not int for v in fields):
        raise Failure(Code.PAGINATION)
    value = Pagination(*fields)
    expected_pages = (value.total + PAGE_SIZE - 1) // PAGE_SIZE
    if (
        value.page != expected_page
        or value.per_page != PAGE_SIZE
        or value.total < 0
        or value.total_pages not in ({0, 1} if value.total == 0 else {expected_pages})
        or (value.total > 0 and value.page > value.total_pages)
        or len(data["items"])
        != min(PAGE_SIZE, max(0, value.total - (value.page - 1) * PAGE_SIZE))
    ):
        raise Failure(Code.PAGINATION)
    if first and (value.total, value.per_page, value.total_pages) != (
        first.total,
        first.per_page,
        first.total_pages,
    ):
        raise Failure(Code.PAGINATION)
    return value


def gtin_valid(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{8}|[0-9]{12,14}", value):
        return False
    total = sum(
        int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(value[:-1]))
    )
    return (10 - total % 10) % 10 == int(value[-1])


def presentation(value):
    if not isinstance(value, str):
        return None, None
    text = normalized(value)
    amounts = re.findall(r"(?<![0-9])([0-9]+(?:[.,][0-9]+)?)\s*(ml|cc|l)\b", text)
    try:
        volumes = {
            Decimal(a.replace(",", ".")) * (1000 if u == "l" else 1) for a, u in amounts
        }
    except InvalidOperation:
        return None, None
    volume = next(iter(volumes)) if len(volumes) == 1 else None
    # Quantity is explicit commercial packaging, never stock, parent flag or SKU.
    amount = r"[0-9]+(?:[.,][0-9]+)?\s*(?:ml|cc|l)"
    unit = re.fullmatch(
        r"(?:unidad(?: individual)?|botella individual)(?: de)?\s+" + amount, text
    )
    pack = re.fullmatch(
        r"(?:(?:pack|caja)\s*)?(?:x\s*)?([0-9]+)\s*(?:x|×|unidades? de)\s*" + amount,
        text,
    )
    pack_before = re.fullmatch(
        r"(?:pack|caja)\s*x?\s*([0-9]+)\s+(?:de\s+)?" + amount, text
    )
    count = (
        1 if unit else int((pack or pack_before)[1]) if pack or pack_before else None
    )
    return volume, count


def native_text(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 1000:
        raise Failure(Code.JSON)
    return value


def assess(parent, variant, page, parent_index, variant_index):
    ident = variant_id(variant.get("id"))
    source = {
        k: native_text(variant.get(k))
        for k in (
            "sku",
            "description",
            "variant_description",
            "barcode",
            "gtin",
            "brand",
        )
    }
    source.update(
        parent_description=native_text(parent.get("description")),
        parent_code=native_text(parent.get("code")),
        parent_brand=native_text(parent.get("brand")),
        is_combo=variant.get("is_combo"),
        parent_is_combo=parent.get("is_combo"),
    )
    errors = []
    name = source["parent_description"]
    brand = source["brand"] or source["parent_brand"]
    if not source["sku"] or not source["sku"].strip():
        errors.append("SKU_MISSING")
    if not name or "stevia" not in re.findall(r"[a-z0-9]+", normalized(name)):
        errors.append("NAME_NOT_CONFIRMED")
    if not brand or normalized(brand) != "hileret":
        errors.append("BRAND_NOT_CONFIRMED")
    if (
        source["brand"]
        and source["parent_brand"]
        and normalized(source["brand"]) != normalized(source["parent_brand"])
    ):
        errors.append("BRAND_CONFLICT")
    barcode, gtin = source["barcode"], source["gtin"]
    if barcode and gtin and barcode != gtin:
        errors.append("BARCODE_GTIN_CONFLICT")
    available = [v for v in (barcode, gtin) if v]
    if not available or any(not gtin_valid(v) for v in available):
        errors.append("EAN_INVALID_OR_MISSING")
    if any(v != BARCODE for v in available):
        errors.append("EAN_NOT_THE_DOCUMENTED_INDIVIDUAL")
    primary = source["variant_description"] or source["description"]
    volume, quantity = presentation(primary)
    if volume != Decimal(200):
        errors.append("PRESENTATION_NOT_CONFIRMED")
    if quantity != 1:
        errors.append("COMMERCIAL_UNIT_COUNT_NOT_CONFIRMED")
    if source["variant_description"] and source["description"]:
        secondary_volume, secondary_quantity = presentation(source["description"])
        if (
            secondary_volume is not None
            and volume is not None
            and secondary_volume != volume
        ) or (
            secondary_quantity is not None
            and quantity is not None
            and secondary_quantity != quantity
        ):
            errors.append("PRESENTATION_CONFLICT")
    if source["is_combo"] is not False:
        errors.append("COMBO_NOT_CONFIRMED_AS_FALSE")
    if source["parent_is_combo"] is not None and source["parent_is_combo"] is not False:
        errors.append("PARENT_COMBO_REQUIRES_REVIEW")
    return {
        "response_variant_id": ident,
        "id_source_path": f"data.items[{parent_index}].variants[{variant_index}].id",
        "response_page": page,
        "source_fields": source,
        "volume_ml_from_presentation": str(volume) if volume is not None else None,
        "commercial_units_from_presentation": quantity,
        "blockers": errors,
        "eligible_for_human_review": not errors,
        "binding_permitted": False,
    }


def candidates(data, page, seen):
    result = []
    for i, parent in enumerate(data["items"]):
        if (
            not isinstance(parent, dict)
            or not isinstance(parent.get("variants"), list)
            or not parent["variants"]
        ):
            raise Failure(Code.JSON)
        for j, variant in enumerate(parent["variants"]):
            if not isinstance(variant, dict):
                raise Failure(Code.JSON)
            row = assess(parent, variant, page, i, j)
            if row["response_variant_id"] in seen:
                raise Failure(Code.ID)
            seen.add(row["response_variant_id"])
            result.append(row)
            if len(seen) > 2000:
                raise Failure(Code.LIMIT)
    return result
