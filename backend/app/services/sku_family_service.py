"""Conservative KIKI Market SKU-family *hints*, not product-identity decisions.

SKU family is an internal commercial grouping. A related family can include combos,
promotions and special prices. Neither this rule nor a shared SKU confirms physical
variants, duplicate catalog rows, GTIN validity or stock synchronization.
"""


def _special_ending(suffix: str) -> bool:
    """Three repeated digits (111..999) or digit followed by '00' (100..900).

    000 is excluded because it does not match 'a digit + two zeros' with a
    nonzero digit. Identical-prefix rules cover e.g. 5028 / 5028000.
    """
    return (
        len(suffix) == 3
        and suffix.isascii()
        and suffix.isdigit()
        and (
            (suffix[0] != "0" and suffix[0] == suffix[1] == suffix[2])
            or (suffix[0] != "0" and suffix[1:] == "00")
        )
    )


def compare_family_skus(left: str, right: str) -> dict:
    """Explain only *potential* SKU family structure, without authorizing decisions.

    Requirements confirmed by KIKI Market:
      - same SKU;
      - same first four digits;
      - same first three digits;
      - first two digits plus a special three-digit ending (111/222/999
        or 100/200/300/etc) as a five-digit SKU.

    Ambiguous, short or alphanumeric SKUs are never inferred as numerical
    family relatives. Prefix-only matches remain candidates for human review.
    """
    a, b = str(left or "").strip(), str(right or "").strip()
    if a and b and a == b:
        return {
            "rule": "SAME_SKU", "related": True,
            "explanation": "Tienen exactamente el mismo SKU.",
        }
    valid = bool(a and b and a.isascii() and b.isascii() and a.isdigit() and b.isdigit())
    if not valid:
        return {
            "rule": "NOT_NUMERIC", "related": False,
            "explanation": "No se pudo aplicar la regla numérica a estos SKU.",
        }
    if len(a) >= 4 and len(b) >= 4 and a[:4] == b[:4]:
        rule, explanation = "PREFIX_4", "Comparten los primeros cuatro dígitos."

    elif len(a) >= 3 and len(b) >= 3 and a[:3] == b[:3]:
        rule, explanation = "PREFIX_3", "Comparten los primeros tres dígitos."
    elif (
        len(a) >= 2 and len(b) >= 2 and a[:2] == b[:2]
        and (
            (len(a) == 5 and _special_ending(a[2:]))
            or (len(b) == 5 and _special_ending(b[2:]))
        )
    ):
        rule, explanation = "PREFIX_2_SPECIAL", (
            "Comparten los primeros dos dígitos y aparece una terminación "
            "especial de familia (tres dígitos repetidos o 100/200/300…)."
        )
    else:
        rule, explanation = "NO_RULE", (
            "No cumplen ninguna coincidencia de familia SKU conocida."
        )
    return {"rule": rule, "related": rule != "NO_RULE", "explanation": explanation}


def diagnose_duplicate_group(products: list[dict]) -> dict:
    """Show pairwise family hints for existing duplicate review groups only.

    Does NOT create or resolve a duplicate, nor change the review decision.
    """
    pairs = []
    for i, first in enumerate(products):
        first_sku = str(
            first.get("sku") or first.get("sku_effective")
            or first.get("sku_variant") or ""
        ).strip()
        for second in products[i + 1:]:
            other_sku = str(
                second.get("sku") or second.get("sku_effective")
                or second.get("sku_variant") or ""
            ).strip()
            match = compare_family_skus(first_sku, other_sku)
            pairs.append({"sku_a": first_sku, "sku_b": other_sku, **match})

    matching = sum(pair["related"] for pair in pairs)
    if pairs and matching == len(pairs):
        status, headline = "FAMILY_CANDIDATE", (
            "La estructura de los SKU es compatible con una familia comercial."
        )
    else:
        status, headline = "REVIEW_REQUIRED", (
            "Hay SKU que no cumplen la regla familiar o no pueden interpretarse."
        )
    return {
        "status": status,
        "headline": headline,
        "pairs": pairs,
        "matches": matching,
        "comparisons": len(pairs),
        "policy": (
            "Posible familia comercial, NO variantes ni duplicados confirmados. "
            "Verificar productos, combos y presentaciones antes de cualquier decisión. "
            "El GTIN/EAN se comprueba por separado."
        ),
    }
