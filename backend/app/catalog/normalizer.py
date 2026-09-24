import math
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

_EMPTY = {"", "NAN", "NONE", "NULL", "N/A", "<NA>"}

def _text(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    if text.upper() in _EMPTY:
        return None
    return text

def normalize_identifier(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    # Excel commonly serializes identifier cells as 123.0.
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    return re.sub(r"\s+", "", text).upper()

def normalize_sku(value: Any) -> str | None:
    return normalize_identifier(value)

def normalize_ean(value: Any) -> str | None:
    text = normalize_identifier(value)
    return re.sub(r"[^0-9]", "", text) if text else None

def normalize_title(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9]+", " ", plain)).strip().upper()

def normalize_decimal(value: Any) -> Decimal | None:
    text = _text(value)
    if not text:
        return None
    cleaned = re.sub(r"[^0-9,.-]", "", text)
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None
