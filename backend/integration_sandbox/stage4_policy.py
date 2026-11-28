"""Opt-in, exact synthetic routes for commercial acceptance; never production."""
import re

IDS = r"(?:91040(?:0[01][0-9]|020|09[1-3])|7518949)"
# The chosen twenty IDs are 9104001 through 9104020; 9104000 is excluded.
EXACT_IDS = frozenset(str(9104000 + n) for n in range(1, 21)) | {
    "9104091", "9104092", "9104093", "7518949",
}
ROOT = "/api/ecomm-app/workspace/"


def route_allowed(method, path):
    if method == "GET" and path == ROOT + "taxonomy/catalog":
        return True
    if method == "POST" and path in {
        ROOT + "taxonomy/catalog", ROOT + "taxonomy/review-preview",
        ROOT + "taxonomy/review-batch", ROOT + "commercial-review/preview",
        ROOT + "commercial-review/apply", ROOT + "exports/commercial/preview",
        ROOT + "exports/commercial/download",
    }:
        return True
    tail = path.removeprefix(ROOT).split("/", 1)
    if not path.startswith(ROOT) or tail[0] not in EXACT_IDS:
        return False
    suffix = tail[1] if len(tail) == 2 else ""
    if method == "GET":
        return suffix in {
            "", "evidence", "proposals", "taxonomy-review", "commercial-coverage",
            "media-review", "channels", "proposals/generation-context",
        } or bool(re.fullmatch(r"documents/local-[a-f0-9]{32}/original/[1-8]", suffix))
    return method == "POST" and (suffix in {
        "", "taxonomy-review", "proposals/generate", "evidence/facts/review-batch",
        "evidence/extract",
    } or bool(re.fullmatch(
        r"(?:documents/local-[a-f0-9]{32}/(?:media-rights|provenance)|"
        r"proposals/[1-9][0-9]{0,9}/review|evidence/facts/[a-f0-9]{24}/review)", suffix
    )))
