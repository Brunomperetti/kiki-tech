"""Conservative pack-count candidate from archived manufacturer HTML.

Only a single visible product H1 plus an explicit product-information paragraph
with the *same* quantity and dosage form can yield a presentation candidate.
No source certification, medical claims, manufacturer inference or media rights.
"""
import re
import unicodedata


PACK = re.compile(
    r"(?<![0-9])(?P<count>[1-9][0-9]{0,3})\s*"
    r"(?P<unit>comprimidos?|comp\.?|c[aá]psulas?|caps\.?|tabletas?)\b",
    re.IGNORECASE,
)


def normalized(text):
    return unicodedata.normalize("NFKD", text).encode(
        "ascii", "ignore"
    ).decode("ascii").casefold()


def pack_of(text):
    matches = set()
    for found in PACK.finditer(text):
        count = int(found.group("count"))
        unit = normalized(found.group("unit")).rstrip(".")
        if unit in {"comp", "comprimido", "comprimidos"}:
            canonical = "comprimidos"
        elif unit in {"caps", "capsula", "capsulas"}:
            canonical = "cápsulas"
        else:
            canonical = "tabletas"
        matches.add((count, canonical))
    return matches


def page_presentation(sections):
    """Return literal quoted presentation candidate or None, fail closed.

    Product-information text may be a list of medical benefits or dosage
    recommendations: it is retained for inspection but NONE of those
    assertions are extracted as claims by this function.
    """
    titles = [
        line.split("Nombre:", 1)[-1].strip()
        for loc, line in sections.items()
        if loc.startswith("web/h1/") and line.startswith("Nombre:")
    ]
    if len(titles) != 1:
        return None
    named = pack_of(titles[0])
    if len(named) != 1:
        return None
    information = [
        (loc, value)
        for loc, value in sections.items()
        if loc.startswith("web/p/")
        and "informacion del producto" in normalized(value[:160])
    ]
    if len(information) != 1:
        return None
    loc, quote = information[0]
    written = pack_of(quote)
    if len(written) != 1 or named != written:
        return None
    count, unit = next(iter(written))
    presentation = f"{count} {unit}"
    # Citation must literally contain the same numeral + dosage form.
    if not PACK.search(quote):
        return None
    return presentation, loc, quote
