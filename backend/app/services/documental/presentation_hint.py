"""Conservative package-size hint for manual manufacturer research only.

Never changes the Ecomm API source, canonical presentation, identity digest,
EAN or approved facts. An exact unit measurement is a LOOKUP HINT, not proof.
"""
import re

QUANTITY = re.compile(
    r"(?<![\w])(?:x\s*)?(\d{1,5}(?:[.,]\d{1,3})?)\s*"
    r"(kg|grs?|gs|g|ml|cc|l|lts?)\b",
    flags=re.IGNORECASE,
)
PACK = re.compile(
    r"\b(?:pack|combo|kit|caja\s*(?:por|de|x)?\s*\d+|"
    r"\d+\s*unidades|x\s*\d+\s*unidades)\b",
    flags=re.IGNORECASE,
)
UNITS = {
    "kg": "kg", "gr": "g", "grs": "g", "gs": "g", "g": "g",
    "ml": "ml", "cc": "ml", "l": "l", "lt": "l", "lts": "l",
}


def candidate(source):
    if source.get("is_combo") is not False or source.get("parent_is_combo") is True:
        return None
    name = source.get("product_name")
    variant = source.get("variant_description")
    if not isinstance(name, str) or not isinstance(variant, str):
        return None
    # Avoid manufacturing a package size from codes, ambiguous packs, or
    # multiple measurements even if the upstream mislabeled the product.
    raw = variant.strip()
    if not raw or PACK.search(raw) or len(raw) > 300:
        return None
    found = QUANTITY.findall(raw)
    if len(found) != 1:
        return None
    quantity, unit = found[0]
    quantity = quantity.replace(",", ".")
    if "." in quantity:
        quantity = quantity.rstrip("0").rstrip(".")
    if not quantity or float(quantity) <= 0:
        return None
    return f"{quantity} {UNITS[unit.lower()]}"
