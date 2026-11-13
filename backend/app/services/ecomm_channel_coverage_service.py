"""Read-only, Ecomm-variant-first coverage matrix for ML API and TN CSV.

A SKU match is NOT a verified linkage or proof of a correct listing. Missing
SKU evidence in old snapshots does NOT prove an item is unpublished. Never
use the historical Ecomm XLSX or ML spreadsheet as a fallback.
"""

from collections import Counter, defaultdict

from sqlalchemy import select

from ..database.models import CatalogSnapshot
from ..integrations.ecomm_app.catalog_stage import STAGE_SOURCE
from .tiendanube_assisted_match_service import (
    normalize,
    variant_conflict,
    pack_units,
    numbers,
)
from .ecomm_api_product_workspace_service import _gtin_check_digit_valid


def _text(value):
    return str(value).strip() if value is not None else ""


def _sku(value):
    return _text(value).casefold()


def _valid_ean(value):
    code = _text(value)
    return code if code and _gtin_check_digit_valid(code) else ""


def channel_sku(channel, row):
    # A parent SKU cannot identify an ML variation. Do not normalize punctuation,
    # leading zeroes or suffixes into a different commercial code.
    if channel == "ml":
        if "#" in _text(row.get("external_id")):
            return _sku(row.get("variant_sku"))
        return _sku(
            row.get("variant_sku")
            or row.get("sku_product")
            or row.get("sku_effective")
            or row.get("sku")
        )
    return _sku(row.get("sku"))


def channel_title(channel, row):
    title = _text(row.get("title" if channel == "ml" else "name"))
    if channel == "tn":
        values = " ".join(
            _text(v.get("value")) for v in row.get("variant", []) if isinstance(v, dict)
        )
        return f"{title} {values}".strip()
    return title


def channel_codes(row):
    return {_valid_ean(row.get(k)) for k in ("ean_raw", "ean", "barcode", "gtin")} - {
        ""
    }


def comparison_bucket(evidence):
    """Exclusive partition of Ecomm variants; never a count of channel listings."""
    if evidence.get("identity_verified"):
        return "verified"
    if evidence.get("evidence_state") == "IDENTITY_CONFLICT" or evidence["status"] in {
        "AMBIGUOUS_API_SKU",
        "MULTIPLE_SKU_ROWS",
    }:
        return "conflicts"
    if evidence.get("snapshot_available") and not evidence.get("freshness", {}).get(
        "fresh"
    ):
        return "stale"
    if evidence.get("candidates_total"):
        return "candidates"
    if (
        evidence.get("snapshot_available")
        and evidence.get("searchable_identity")
        and evidence.get("capture_searchable")
    ):
        return "no_match"
    return "insufficient"


def _candidate_index(channel, rows):
    indices = {
        key: defaultdict(set) for key in ("sku", "gtin", "title", "words", "numbers")
    }
    valid = {}
    for position, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        valid[position] = row
        sku = channel_sku(channel, row)
        if sku:
            indices["sku"][sku].add(position)
        for code in channel_codes(row):
            indices["gtin"][code].add(position)
        title = normalize(channel_title(channel, row))
        if title:
            indices["title"][title].add(position)
        for number in numbers(channel_title(channel, row)):
            indices["numbers"][number].add(position)
        # Brand AND at least two discriminating title words are required for
        # lexical candidates. This is retrieval, never identity approval.
        for word in set(title.split()):
            if len(word) >= 4 and not word.isdigit():
                indices["words"][word].add(position)
    return valid, indices


def _find_candidates(identity, valid, indices):
    sku = _sku(identity.get("sku"))
    code = (
        _valid_ean(identity.get("gtin"))
        if not identity.get("identity_blockers")
        else ""
    )
    title = normalize(
        f"{identity.get('product_name') or ''} {identity.get('variant_description') or ''}"
    )
    names = {title, normalize(identity.get("product_name"))} - {""}
    reasons = defaultdict(set)
    for position in indices["sku"].get(sku, ()):
        reasons[position].add("SKU_EXACT")
    for position in indices["gtin"].get(code, ()):
        reasons[position].add("VALID_GTIN_EXACT")
    strong = bool(reasons)
    for name in names:
        positions = indices["title"].get(name, set())
        if strong:
            positions = positions & reasons.keys()
        for position in positions:
            reasons[position].add("TITLE_EXACT")
    brand = normalize(identity.get("brand"))
    words = {w for w in title.split() if len(w) >= 4 and not w.isdigit()} - set(
        brand.split()
    )
    # Intersect posting lists, avoiding a full channel scan for every variant.
    # With an exact code hit, title/brand remain comparison evidence rather than
    # adding every similar product in the same family (quadratic noise).
    distinguishing_numbers = numbers(identity.get("product_name")) - numbers(
        identity.get("variant_description")
    )
    numeric_scope = None
    for number in distinguishing_numbers:
        posting = indices["numbers"].get(number, set())
        numeric_scope = posting if numeric_scope is None else numeric_scope & posting
    votes = (
        Counter(
            position
            for word in words
            for position in (
                indices["words"].get(word, set())
                if numeric_scope is None
                else indices["words"].get(word, set()) & numeric_scope
            )
        )
        if brand and not strong
        else Counter()
    )
    for position, count in votes.items():
        if (
            count >= 2
            and count >= len(words) * 0.6
            and brand
            and normalize(valid[position].get("brand")) == brand
            and distinguishing_numbers.issubset(
                numbers(
                    channel_title(
                        "ml" if "external_id" in valid[position] else "tn",
                        valid[position],
                    )
                )
            )
            and pack_units(identity.get("variant_description"))
            and not variant_conflict(
                title,
                identity.get("sku"),
                channel_title(
                    "ml" if "external_id" in valid[position] else "tn", valid[position]
                ),
                valid[position].get("sku"),
            )
        ):
            reasons[position].add("BRAND_AND_TITLE_WORDS")
    # Exact title by itself is eligible only with explicit brand/presentation
    # evidence, or as corroboration of a code match. No family-SKU fuzzy match.
    for position in list(reasons):
        if reasons[position] == {"TITLE_EXACT"} and (
            not brand or normalize(valid[position].get("brand")) != brand
        ):
            del reasons[position]
    positions = sorted(
        reasons,
        key=lambda i: (
            -int("SKU_EXACT" in reasons[i]),
            -int("VALID_GTIN_EXACT" in reasons[i]),
            i,
        ),
    )
    return (
        [valid[i] for i in positions],
        {id(valid[i]): sorted(reasons[i]) for i in positions},
        positions,
    )


def _review_candidate(candidate, source_name, source_sku, *, is_combo, source_gtin):
    # SKU never establishes equality of presentation, pack, manufacturer or GTIN.
    actual_name = _text(candidate.get("name") or candidate.get("title"))
    if source_gtin and _text(
        candidate.get("ean_raw")
        or candidate.get("ean")
        or candidate.get("gtin")
        or candidate.get("barcode")
    ):
        other = _text(
            candidate.get("ean_raw")
            or candidate.get("ean")
            or candidate.get("gtin")
            or candidate.get("barcode")
        )
        if _valid_ean(source_gtin) and _valid_ean(other) and source_gtin != other:
            return "GTIN_CONFLICT"
    if actual_name and variant_conflict(
        source_name, source_sku, actual_name, source_sku
    ):
        return "PRESENTATION_CONFLICT"
    # A pack needs proof of composition; a matching string is insufficient.
    if is_combo:
        return "PACK_REVIEW"
    return "SKU_CANDIDATE"


def _channel_result(
    rows,
    *,
    snapshot_available,
    original_name,
    sku,
    is_combo,
    source_gtin,
    ambiguous_api_sku,
    name_field,
    snapshot_at,
    source,
):
    base = {
        "source": source,
        "snapshot_available": snapshot_available,
        "snapshot_at": snapshot_at,
        "status": "UNAVAILABLE",
        "matching_rows": 0,
        "listing_ids": [],
        "candidate_name": None,
        "candidate_quality": {
            "title_present": False,
            "brand_present": False,
            "description_present": False,
            "ean_present": False,
        },
        "note": "",
        "confirmed_listing": False,
    }
    if not snapshot_available:
        return {
            **base,
            "note": "Falta una captura del canal. No se puede afirmar si está publicado.",
        }
    if ambiguous_api_sku:
        return {
            **base,
            "status": "AMBIGUOUS_API_SKU",
            "matching_rows": len(rows),
            "listing_ids": [_text(r.get("external_id") or r.get("slug")) for r in rows[:8]],
            "note": "El SKU Ecomm tiene varios dueños. Se muestran candidatos sin asignar publicaciones.",
        }
    if not rows:
        return {
            **base,
            "status": "NO_EXACT_SKU_IN_SNAPSHOT",
            "note": "Sin coincidencia por SKU exacto en la copia; NO prueba ausencia real de publicación.",
        }
    if len(rows) != 1:
        return {
            **base,
            "status": "MULTIPLE_SKU_ROWS",
            "matching_rows": len(rows),
            "listing_ids": [
                _text(row.get("external_id") or row.get("slug")) for row in rows
            ][:8],
            "note": "El SKU apunta a varias filas del canal. Revisar variantes y duplicados.",
        }
    row = rows[0]
    kind = _review_candidate(
        row, original_name, sku, is_combo=is_combo, source_gtin=source_gtin
    )
    note = {
        "SKU_CANDIDATE": "SKU único exacto, identidad comercial pendiente de verificar.",
        "PACK_REVIEW": "Pack/combos: verificar composición y presentación antes de vincular.",
        "PRESENTATION_CONFLICT": "SKU igual, posible diferencia de contenido, sabor o presentación.",
        "GTIN_CONFLICT": "SKU igual, pero los GTIN válidos informados son diferentes.",
    }[kind]
    return {
        **base,
        "status": kind,
        "matching_rows": 1,
        "listing_ids": [_text(row.get("external_id") or row.get("slug"))],
        "candidate_name": _text(row.get(name_field)) or None,
        "candidate_quality": {
            "title_present": bool(_text(row.get(name_field))),
            "brand_present": bool(_text(row.get("brand"))),
            "description_present": bool(row.get("description_present"))
            if source == "TIENDANUBE_CSV"
            else False,
            "ean_present": bool(_valid_ean(row.get("ean_raw") or row.get("ean"))),
        },
        "note": note,
        "confirmed_listing": False,
        "listing_statuses": [_text(row.get("status"))]
        if source == "MERCADOLIBRE_API"
        else [],
    }


def build_channel_coverage(
    db,
    pages,
    *,
    api_validation=False,
    edits=None,
    now=None,
    snapshots=None,
    include_reverse=False,
):
    """Map all API variant IDs to independently classified channel evidence."""
    ml_snap = (
        snapshots.get("MERCADOLIBRE_API")
        if snapshots is not None
        else db.scalar(
            select(CatalogSnapshot).where(CatalogSnapshot.source == "MERCADOLIBRE_API")
        )
    )
    tn_snap = (
        snapshots.get("TIENDANUBE")
        if snapshots is not None
        else db.scalar(
            select(CatalogSnapshot).where(CatalogSnapshot.source == "TIENDANUBE")
        )
    )
    ml_rows = ml_snap.payload if ml_snap and isinstance(ml_snap.payload, list) else []
    tn_rows = tn_snap.payload if tn_snap and isinstance(tn_snap.payload, list) else []
    ml_available = ml_snap is not None and isinstance(ml_snap.payload, list)
    tn_available = tn_snap is not None and isinstance(tn_snap.payload, list)

    from datetime import datetime, timezone
    from .ecomm_api_channel_evidence import (
        load_reviews,
        source_identity,
        enrich,
        row_key,
        age_info,
    )

    reviews = (
        load_reviews(db)
        if api_validation
        else {"ml": {}, "tn": {}, "legacy_ignored": 0}
    )
    reviews["row_counts"] = {
        "ml": Counter(row_key("ml", r) for r in ml_rows if isinstance(r, dict)),
        "tn": Counter(row_key("tn", r) for r in tn_rows if isinstance(r, dict)),
    }
    reviewed_positions = {"ml": defaultdict(list), "tn": defaultdict(list)}
    now = now or datetime.now(timezone.utc)
    edits = edits or {}

    sku_owners = Counter()
    for page in pages:
        for parent in page.get("items") or []:
            for v in parent.get("variants") or []:
                if isinstance(v, dict) and not v.get("invalid") and _sku(v.get("sku")):
                    sku_owners[_sku(v["sku"])] += 1

    ml_valid, ml_index = _candidate_index("ml", ml_rows)
    tn_valid, tn_index = _candidate_index("tn", tn_rows)
    for channel, valid in [("ml", ml_valid), ("tn", tn_valid)]:
        for position, row in valid.items():
            from .ecomm_api_channel_evidence import decision_key, PROFILE

            record = reviews[channel].get(decision_key(channel, row))
            if record and (record.source_snapshot or {}).get("profile") == PROFILE:
                target = record.ecomm_id if channel == "ml" else record.target_ecomm_id
                if target:
                    reviewed_positions[channel][str(target)].append(position)
    ml_variations_missing_sku = sum(
        "#" in _text(r.get("external_id")) and not channel_sku("ml", r)
        for r in ml_valid.values()
    )
    matched_positions = {"ml": set(), "tn": set()}
    reverse = {"ml": defaultdict(list), "tn": defaultdict(list)}
    pairs = Counter()
    buckets = {"ml": Counter(), "tn": Counter()}

    searchable = {
        channel: len(valid) == len(ml_rows if channel == "ml" else tn_rows)
        and (
            not valid
            or any(
                channel_sku(channel, r)
                or channel_codes(r)
                or (r.get("brand") and channel_title(channel, r))
                for r in valid.values()
            )
        )
        for channel, valid in [("ml", ml_valid), ("tn", tn_valid)]
    }
    records = {}
    totals = {"ml": Counter(), "tn": Counter(), "combined": Counter()}
    for page in pages:
        for parent in page.get("items") or []:
            if not isinstance(parent, dict):
                continue
            for var in parent.get("variants") or []:
                if not isinstance(var, dict) or var.get("invalid"):
                    continue
                ident = _text(var.get("id"))
                sku = _text(var.get("sku"))
                from ..integrations.ecomm_app.api_catalog_browser import (
                    valid_variant_id,
                )

                if not valid_variant_id(ident) or ident in records:
                    raise ValueError(
                        "Ecomm ID inválido o repetido; no se fusionan variantes."
                    )
                name = _text(
                    parent.get("description") or var.get("variant_description")
                )
                combo = var.get("is_combo") is True or parent.get("is_combo") is True
                gtin = _text(var.get("gtin") or var.get("barcode"))
                ambiguous = bool(sku and sku_owners[_sku(sku)] != 1)
                identity = source_identity(
                    parent, var, page.get("captured_at"), edits.get(ident)
                )
                ml_matches, ml_signals, ml_positions = _find_candidates(
                    identity, ml_valid, ml_index
                )
                tn_matches, tn_signals, tn_positions = _find_candidates(
                    identity, tn_valid, tn_index
                )
                for channel, matches, signals, positions, valid in [
                    ("ml", ml_matches, ml_signals, ml_positions, ml_valid),
                    ("tn", tn_matches, tn_signals, tn_positions, tn_valid),
                ]:
                    for position in reviewed_positions[channel].get(ident, []):
                        if position not in positions:
                            matches.append(valid[position])
                            positions.append(position)
                            signals[id(valid[position])] = ["PREVIOUS_MANUAL_REVIEW"]
                ml = _channel_result(
                    ml_matches,
                    snapshot_available=ml_available,
                    original_name=name,
                    sku=sku,
                    is_combo=combo,
                    source_gtin=gtin,
                    ambiguous_api_sku=ambiguous,
                    name_field="title",
                    snapshot_at=ml_snap.updated_at.isoformat() if ml_snap else None,
                    source="MERCADOLIBRE_API",
                )
                tn = _channel_result(
                    tn_matches,
                    snapshot_available=tn_available,
                    original_name=name,
                    sku=sku,
                    is_combo=combo,
                    source_gtin=gtin,
                    ambiguous_api_sku=ambiguous,
                    name_field="name",
                    snapshot_at=tn_snap.updated_at.isoformat() if tn_snap else None,
                    source="TIENDANUBE_CSV",
                )
                for channel, base, matches, signals, positions in [
                    ("ml", ml, ml_matches, ml_signals, ml_positions),
                    ("tn", tn, tn_matches, tn_signals, tn_positions),
                ]:
                    base["searchable_identity"] = bool(
                        sku or _valid_ean(gtin) or (identity.get("brand") and name)
                    )
                    base["capture_searchable"] = searchable[channel]
                    result = enrich(
                        base,
                        channel,
                        matches,
                        identity,
                        reviews,
                        now,
                        match_signals=signals,
                    )
                    result["comparison_state"] = comparison_bucket(result)
                    buckets[channel][result["comparison_state"]] += 1
                    matched_positions[channel].update(positions)
                    if include_reverse:
                        for position in positions:
                            reverse[channel][position].append(ident)
                    pairs[channel] += len(matches)
                    if channel == "ml":
                        ml = result
                    else:
                        tn = result
                both_candidate = (
                    ml["status"] == "SKU_CANDIDATE" and tn["status"] == "SKU_CANDIDATE"
                )
                neither_exact = (
                    ml["status"] == "NO_EXACT_SKU_IN_SNAPSHOT"
                    and tn["status"] == "NO_EXACT_SKU_IN_SNAPSHOT"
                )
                risk = any(
                    item["status"]
                    in (
                        "MULTIPLE_SKU_ROWS",
                        "PRESENTATION_CONFLICT",
                        "GTIN_CONFLICT",
                        "PACK_REVIEW",
                        "AMBIGUOUS_API_SKU",
                    )
                    for item in (ml, tn)
                )
                combined = (
                    "IDENTITY_REVIEW"
                    if risk
                    else "BOTH_CHANNELS_CANDIDATE"
                    if both_candidate
                    else "NO_EXACT_EVIDENCE_IN_BOTH_SNAPSHOTS"
                    if neither_exact
                    else "SOURCES_UNAVAILABLE"
                    if not ml_available and not tn_available
                    else "PARTIAL_CHANNEL_EVIDENCE"
                )
                totals["ml"][ml["status"]] += 1
                totals["tn"][tn["status"]] += 1
                totals["combined"][combined] += 1
                records[ident] = {
                    "ecomm_id": ident,
                    "sku": sku,
                    "ml": ml,
                    "tn": tn,
                    **({"identity": identity} if api_validation else {}),
                    "combined": combined,
                    "review_required": risk
                    or any(c["comparison_state"] == "conflicts" for c in (ml, tn)),
                    "never_confirmed_by_sku_alone": True,
                }

    comparison = {}
    for channel, rows, valid, snap in [
        ("ml", ml_rows, ml_valid, ml_snap),
        ("tn", tn_rows, tn_valid, tn_snap),
    ]:
        verified_keys = {
            c["id"]
            for r in records.values()
            for c in r[channel].get("candidates", [])
            if c["identity_verified"]
        }
        confirmed_ids = {
            c["id"].split("#")[0]
            for r in records.values()
            for c in r[channel].get("candidates", [])
            if c["identity_verified"]
            and channel == "ml"
            and c["listing_status"] == "active"
        }
        comparison[channel] = {
            "variants": len(records),
            "variant_states": {
                k: buckets[channel][k]
                for k in (
                    "verified",
                    "candidates",
                    "conflicts",
                    "no_match",
                    "insufficient",
                    "stale",
                )
            },
            "captured_records": len(rows),
            "valid_records": len(valid),
            "invalid_records": len(rows) - len(valid),
            "distinct_publications": len(
                {
                    _text(r.get("external_id")).split("#")[0]
                    if channel == "ml"
                    else _text(r.get("slug"))
                    for r in valid.values()
                }
                - {""}
            ),
            "records_without_sku": sum(
                not channel_sku(channel, r) for r in valid.values()
            ),
            "records_without_valid_gtin": sum(
                not channel_codes(r) for r in valid.values()
            ),
            "candidate_pairs": pairs[channel],
            "records_with_candidates": len(matched_positions[channel]),
            "records_without_candidate": len(valid) - len(matched_positions[channel]),
            "verified_records": len(verified_keys),
            "confirmed_publications": len(confirmed_ids),
            "variants_with_candidates": sum(
                r[channel]["candidates_total"] > 0 for r in records.values()
            ),
            "snapshot_at": snap.updated_at.isoformat() if snap else None,
            "freshness": age_info(
                snap.updated_at.isoformat() if snap else None, channel, now
            ),
            "publication_observable": channel == "ml",
        }
        assert sum(comparison[channel]["variant_states"].values()) == len(records)
        assert comparison[channel]["records_with_candidates"] + comparison[channel][
            "records_without_candidate"
        ] == len(valid)

    return {
        "items_by_id": records,
        **({"candidate_ids_by_position": reverse} if include_reverse else {}),
        "api_validation_enabled": api_validation,
        "summary": {
            "api_variants": len(records),
            "comparison": comparison,
            "ml": dict(totals["ml"]),
            "tn": dict(totals["tn"]),
            "combined": dict(totals["combined"]),
            "ml_rows_unmatchable_variation_sku": ml_variations_missing_sku,
            "confirmed_ml_listings": sum(
                r["ml"].get("confirmed_listing_count", 0) for r in records.values()
            ),
            "verified_tn_rows": sum(
                sum(c["identity_verified"] for c in r["tn"].get("candidates", []))
                for r in records.values()
            ),
            "tn_publication_observable": False,
        },
        "sources": {
            "ecomm": STAGE_SOURCE,
            "ml": {
                "name": "MERCADOLIBRE_API",
                "available": ml_available,
                "updated_at": ml_snap.updated_at.isoformat() if ml_snap else None,
                "rows": len(ml_rows),
                "freshness": comparison["ml"]["freshness"],
            },
            "tn": {
                "name": "TIENDANUBE_CSV",
                "available": tn_available,
                "updated_at": tn_snap.updated_at.isoformat() if tn_snap else None,
                "rows": len(tn_rows),
                "freshness": comparison["tn"]["freshness"],
            },
        },
        "policy": (
            "Matriz por Ecomm ID: candidatos por SKU exacto, GTIN válido y señales de nombre/marca; no vínculos aprobados. "
            "Un SKU no confirma presentación o composición; múltiples publicaciones "
            "o packs exigen revisión. Una copia antigua sin coincidencia no demuestra "
            "que el producto no esté publicado. No se consulta Excel Ecomm ni ML."
        ),
    }
