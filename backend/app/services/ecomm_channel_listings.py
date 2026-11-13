"""All captured channel records, including unlinked rows. Existing evidence rules only."""

from datetime import datetime, timezone
from sqlalchemy import select
from app.database.models import CatalogSnapshot, EcommApiProductEdit
from app.integrations.ecomm_app.catalog_stage import STAGE_SOURCE, stage_status
from .ecomm_channel_coverage_service import build_channel_coverage, channel_sku, channel_codes
from .ecomm_api_channel_evidence import row_key, age_info


def listings(db, channel, *, query="", page=1, limit=25, linkage="all"):
    if channel not in {"ml", "tn"} or linkage not in {
        "all",
        "unlinked",
        "verified",
        "candidates",
        "conflicts",
        "no_match",
        "stale",
    }:
        raise ValueError("Canal o filtro de vinculación inválido.")
    if len(query) > 80 or not 1 <= page <= 100000 or not 1 <= limit <= 50:
        raise ValueError("Consulta o paginación fuera de límites.")
    snapshots = {
        r.source: r
        for r in db.scalars(
            select(CatalogSnapshot).where(
                CatalogSnapshot.source.in_(
                    [STAGE_SOURCE, "MERCADOLIBRE_API", "TIENDANUBE"]
                )
            )
        )
    }
    ecomm = snapshots.get(STAGE_SOURCE)
    snap = snapshots.get("MERCADOLIBRE_API" if channel == "ml" else "TIENDANUBE")
    if snap is not None and (
        not isinstance(snap.payload, list)
        or any(not isinstance(r, dict) for r in snap.payload)
    ):
        raise ValueError(
            "Captura de canal inválida; no se informa un catálogo vacío como reemplazo."
        )
    rows = snap.payload if snap and isinstance(snap.payload, list) else []
    if db.bind.dialect.name == "postgresql":
        from .editorial_batches.queue_projection import queue_edits

        edits = queue_edits(db)
    else:
        edits = {e.ecomm_id: e for e in db.scalars(select(EcommApiProductEdit))}
    pages = ecomm.payload if ecomm else []
    quality = stage_status(pages)
    valid_master = quality["complete"] and not quality["quality"].get(
        "duplicate_variant_ids"
    )
    coverage = build_channel_coverage(
        db,
        pages if valid_master else [],
        api_validation=True,
        edits=edits,
        snapshots=snapshots,
        include_reverse=True,
    )
    verified = {}
    for ident, item in coverage["items_by_id"].items():
        for candidate in item[channel]["candidates"]:
            if candidate["identity_verified"]:
                verified.setdefault(candidate["id"], set()).add(ident)
    at = snap.updated_at.isoformat() if snap else None
    age = age_info(at, channel, datetime.now(timezone.utc))
    result = []
    parents = set()
    for position, raw in enumerate(rows):
        if not isinstance(raw, dict):
            continue
        key = row_key(channel, raw)
        actual_id = (
            str(raw.get("external_id") or "").strip()
            if channel == "ml"
            else str(raw.get("slug") or "").strip()
        )
        if actual_id:
            parents.add(actual_id.split("#")[0] if channel == "ml" else actual_id)
        ids = sorted(verified.get(key, []))
        candidate_ids = coverage["candidate_ids_by_position"][channel].get(position, [])
        conflict = any(
            coverage["items_by_id"][ident][channel]["comparison_state"] == "conflicts"
            for ident in candidate_ids
        )
        title = str(raw.get("title" if channel == "ml" else "name") or "").strip()
        sku = str(
            raw.get("variant_sku")
            or raw.get("sku_effective")
            or raw.get("sku_product")
            or raw.get("sku")
            or ""
        ).strip()
        status = raw.get("status") if channel == "ml" else None
        state = (
            "CONFIRMED_CAPTURE"
            if channel == "ml" and ids and status == "active" and age["fresh"]
            else "STALE"
            if snap and not age["fresh"]
            else "VERIFIED_LINK"
            if ids
            else "PENDING_VALIDATION"
            if conflict
            else "CANDIDATE"
            if candidate_ids
            else "NO_MATCH_IN_CAPTURE"
            if valid_master and (channel_sku(channel, raw) or channel_codes(raw))
            else "INSUFFICIENT_EVIDENCE"
        )
        row = {
            "position": position,
            "id": actual_id or None,
            "title": title or None,
            "sku": sku or None,
            "ecomm_ids": ids,
            "candidate_ecomm_ids": candidate_ids[:50],
            "candidate_variants_total": len(candidate_ids),
            "candidate_variants_truncated": len(candidate_ids) > 50,
            "identity_ambiguous": conflict,
            "listing_status": status,
            "evidence_state": state,
            "captured_at": at,
            "confirmed_listing": state == "CONFIRMED_CAPTURE",
        }
        if (
            query.strip()
            and query.strip().casefold()
            not in " ".join([actual_id, title, sku, *ids]).casefold()
        ):
            continue
        if linkage == "unlinked" and ids or linkage == "verified" and not ids:
            continue
        if linkage == "candidates" and not candidate_ids:
            continue
        if linkage == "conflicts" and not conflict:
            continue
        if linkage == "no_match" and candidate_ids:
            continue
        if linkage == "stale" and age["fresh"]:
            continue
        result.append(row)
    offset = (page - 1) * limit
    return {
        "comparison": coverage["summary"]["comparison"][channel],
        "channel": channel,
        "source": "MERCADOLIBRE_API" if channel == "ml" else "TIENDANUBE_CSV",
        "available": snap is not None,
        "master_available": valid_master,
        "captured_at": at,
        "freshness": age,
        "total_records": len(rows),
        "distinct_publications": len(parents),
        "matches": len(result),
        "page": page,
        "limit": limit,
        "query": query.strip(),
        "linkage": linkage,
        "items": result[offset : offset + limit],
        "external_writes_enabled": False,
        "scope": "CAPTURED_CHANNEL_RECORDS",
        "policy": "Captura, no consulta en vivo. SKU/EAN no confirman vínculos. Un CSV no demuestra publicación actual. Sin Ecomm ID validado no se crea una identidad ficticia.",
    }
