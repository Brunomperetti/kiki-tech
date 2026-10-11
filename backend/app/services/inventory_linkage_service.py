from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
import re

from sqlalchemy.orm import Session

from ..catalog.normalizer import normalize_title
from ..database.models import InventoryLinkageDecision
from ..repositories.catalog_repository import CatalogRepository


class InventoryLinkageService:
    """Cross EDIMA publication linkage state with canonical Ecomm products by GTIN."""

    READY_TO_LINK = "READY_TO_LINK"
    REVIEW_AMBIGUOUS = "REVIEW_AMBIGUOUS"
    REVIEW_MULTIPLE_GTIN = "REVIEW_MULTIPLE_GTIN"
    REVIEW_IDENTIFIER_CONFLICT = "REVIEW_IDENTIFIER_CONFLICT"
    REVIEW_TITLE_CANDIDATE = "REVIEW_TITLE_CANDIDATE"
    REVIEW_OFFLINE_CANDIDATE = "REVIEW_OFFLINE_CANDIDATE"
    REVIEW_PRESENTATION_CONFLICT = "REVIEW_PRESENTATION_CONFLICT"
    PENDING_ECOMM_CATALOG = "PENDING_ECOMM_CATALOG"
    INVALID_GTIN = "INVALID_GTIN"
    NO_ECOMM_MATCH = "NO_ECOMM_MATCH"

    def __init__(self, db: Session):
        self.db = db
        self.repo = CatalogRepository(db)

    def report(self, apply_decisions: bool = True) -> dict:
        edima = self.repo.snapshot("EDIMA_LINKAGE")
        products = self.repo.snapshot("ECOMM_APP")
        offline_evidence = self.repo.snapshot("OFFLINE_LINKAGE_EVIDENCE")
        if not edima:
            return self._unavailable(
                "Importá el reporte EDIMA de Mercado Libre para analizar la vinculación de inventario."
            )
        if not products:
            return self._unavailable(
                "Importá primero el catálogo de Ecomm-App para cruzar los GTIN de EDIMA."
            )

        product_by_ecomm_id = {
            str(product.get("ecomm_id") or "").strip(): product
            for product in products
            if str(product.get("ecomm_id") or "").strip()
        }
        offline_by_mla = {
            str(item.get("external_id") or "").strip(): item
            for item in offline_evidence
            if str(item.get("external_id") or "").strip()
        }

        ean_index: dict[str, list[dict]] = defaultdict(list)
        listing_index: dict[str, list[dict]] = defaultdict(list)
        reconciliation_index: dict[str, list[dict]] = defaultdict(list)
        for product in products:
            seen = set()
            for ean in [product.get("ean"), *(product.get("ean_aliases") or [])]:
                value = str(ean or "").strip()
                if value and value not in seen:
                    ean_index[value].append(product)
                    seen.add(value)
            listing_seen = set()
            for ecomm_row in product.get("ecomm_rows") or []:
                for raw_id in [ecomm_row.get("listing_id"), ecomm_row.get("marketplace_id")]:
                    for key in self._listing_keys(raw_id):
                        if key not in listing_seen:
                            listing_index[key].append(product)
                            listing_seen.add(key)

        title_index: dict[str, list[dict]] = defaultdict(list)
        normalized_products: list[tuple[dict, str]] = []
        for product in products:
            normalized = normalize_title(product.get("name"))
            if normalized:
                title_index[normalized].append(product)
                normalized_products.append((product, normalized))

        latest_run = self.repo.latest_run()
        if latest_run:
            for result in latest_run.results or []:
                product = result.get("product")
                if not product:
                    continue
                raw_ids = list(result.get("matched_listing_ids") or [])
                listing = result.get("listing") or {}
                if listing.get("external_id"):
                    raw_ids.append(listing.get("external_id"))
                for raw_id in raw_ids:
                    for key in self._listing_keys(raw_id):
                        reconciliation_index[key].append(product)

        decisions = (
            {
                decision.external_id: decision
                for decision in self.db.query(InventoryLinkageDecision).all()
            }
            if apply_decisions
            else {}
        )
        confirmed_by_human = 0

        linked = 0
        unlinked = 0
        invalid_gtin_total = 0
        multiple_gtin_total = 0
        unlinked_gtins = set()
        status_counts: Counter[str] = Counter()
        items = []

        for row in edima:
            gtins = [str(value).strip() for value in row.get("gtins") or [] if str(value).strip()]
            valid_gtins = [value for value in gtins if self._valid_gtin(value)]
            if not gtins or len(valid_gtins) != len(gtins):
                invalid_gtin_total += 1
            if len(gtins) > 1:
                multiple_gtin_total += 1

            if self._is_linked(row.get("inventory_linked")):
                linked += 1
                continue

            unlinked += 1
            unlinked_gtins.update(valid_gtins)
            status, reason, matched, match_method = self._classify_unlinked(
                row,
                gtins,
                valid_gtins,
                ean_index,
                listing_index,
                reconciliation_index,
                title_index,
                normalized_products,
            )
            offline_item = offline_by_mla.get(str(row.get("external_id") or "").strip())
            if status == self.NO_ECOMM_MATCH and offline_item:
                offline_candidate = product_by_ecomm_id.get(
                    str(offline_item.get("candidate_ecomm_id") or "").strip()
                )
                if offline_candidate:
                    matched = offline_candidate
                    status = self.REVIEW_OFFLINE_CANDIDATE
                    evidence_type = str(offline_item.get("evidence_type") or "").strip()
                    match_method = f"OFFLINE_{evidence_type or 'REFERENCE'}"
                    reason = (
                        "El documento de control offline propone este producto Ecomm como candidato. "
                        "Requiere confirmación humana antes de usarlo para vinculación."
                    )
            decision_status = "NONE"
            decision_note = None
            decision_at = None
            decision_source = "AUTOMATIC_IDENTIFIERS" if status == self.READY_TO_LINK else "NONE"
            decision = decisions.get(str(row.get("external_id") or ""))
            pending_ecomm_decision = (
                decision
                and decision.decision == "NO_ECOMM_PRODUCT"
                and status == self.NO_ECOMM_MATCH
            )
            if pending_ecomm_decision:
                snapshot = decision.source_snapshot or {}
                same_source = (
                    str(snapshot.get("title") or "") == str(row.get("title") or "")
                    and str(snapshot.get("gtin_raw") or "") == str(row.get("gtin_raw") or "")
                )
                decision_note = decision.note
                decision_at = decision.updated_at.isoformat() if decision.updated_at else None
                decision_source = "HUMAN_KIKI"
                if same_source:
                    decision_status = "PENDING_ECOMM"
                    status = self.PENDING_ECOMM_CATALOG
                    reason = (
                        "Revisado humanamente: no se encontró una coincidencia válida en el catálogo "
                        "Ecomm actual. Requiere alta/corrección en Ecomm o importar un inventario más "
                        "nuevo antes de intentar vincular."
                    )
                    match_method = "HUMAN_NO_ECOMM_MATCH"
                else:
                    decision_status = "STALE"
            manual_decision = (
                decision
                and (decision.source_snapshot or {}).get("match_method") == "MANUAL_SEARCH"
            )
            if not pending_ecomm_decision and manual_decision and status != self.READY_TO_LINK:
                manual_product = product_by_ecomm_id.get(str(decision.ecomm_id or "").strip())
                if manual_product:
                    decision_status = self._decision_state(decision, row, manual_product)
                    decision_note = decision.note
                    decision_at = decision.updated_at.isoformat() if decision.updated_at else None
                    decision_source = "HUMAN_KIKI"
                    if decision_status == "CONFIRMED":
                        matched = manual_product
                        status = self.READY_TO_LINK
                        match_method = "HUMAN_CONFIRMED_MANUAL"
                        confirmed_by_human += 1
                        reason = (
                            "Producto Ecomm elegido y confirmado manualmente dentro de KIKI Tech. "
                            "La publicación queda lista para el siguiente paso de vinculación asistida."
                        )
                    elif decision_status == "STALE":
                        reason = (
                            "La asignación manual anterior quedó desactualizada porque cambió el EDIMA. "
                            "Debe revisarse nuevamente."
                        )
            elif (
                not pending_ecomm_decision
                and decision
                and status
                in {self.REVIEW_TITLE_CANDIDATE, self.REVIEW_OFFLINE_CANDIDATE}
                and matched is not None
            ):
                decision_status = self._decision_state(decision, row, matched)
                decision_note = decision.note
                decision_at = decision.updated_at.isoformat() if decision.updated_at else None
                decision_source = "HUMAN_KIKI"
                if decision_status == "CONFIRMED":
                    original_method = match_method
                    status = self.READY_TO_LINK
                    match_method = (
                        "HUMAN_CONFIRMED_OFFLINE"
                        if str(original_method or "").startswith("OFFLINE_")
                        else "HUMAN_CONFIRMED_TITLE"
                    )
                    confirmed_by_human += 1
                    reason = (
                        "Coincidencia confirmada humanamente dentro de KIKI Tech. "
                        "La publicación queda lista para el siguiente paso de vinculación asistida."
                    )
                elif decision_status == "REJECTED":
                    reason = (
                        "El candidato sugerido fue rechazado humanamente. "
                        "La publicación sigue requiriendo identificación."
                    )
                elif decision_status == "STALE":
                    reason = (
                        "Existe una decisión anterior, pero cambió el EDIMA o el producto sugerido. "
                        "Debe revisarse nuevamente antes de usarla."
                    )

            if matched is not None and status == self.READY_TO_LINK:
                product_issue = self._product_identity_conflict(
                    row.get("title"),
                    matched.get("name"),
                )
                if product_issue:
                    status = self.REVIEW_PRESENTATION_CONFLICT
                    reason = product_issue
                    match_method = f"{match_method}_PRESENTATION_CONFLICT"
                    if decision_status == "CONFIRMED":
                        decision_status = "STALE"

            status_counts[status] += 1
            items.append(
                {
                    "external_id": row.get("external_id"),
                    "variation_id": row.get("variation_id"),
                    "title": row.get("title"),
                    "brand": row.get("brand"),
                    "gtin_raw": row.get("gtin_raw"),
                    "gtins": gtins,
                    "inventory_linked": row.get("inventory_linked"),
                    "modified_at": row.get("modified_at"),
                    "status": status,
                    "reason": reason,
                    "match_method": match_method,
                    "offline_evidence": offline_item or None,
                    "decision_status": decision_status,
                    "decision_note": decision_note,
                    "decision_at": decision_at,
                    "decision_source": decision_source,
                    "matched_product": self._product_view(matched) if matched else None,
                }
            )

        order = {
            self.READY_TO_LINK: 0,
            self.NO_ECOMM_MATCH: 1,
            self.REVIEW_AMBIGUOUS: 2,
            self.REVIEW_MULTIPLE_GTIN: 3,
            self.REVIEW_IDENTIFIER_CONFLICT: 4,
            self.REVIEW_TITLE_CANDIDATE: 5,
            self.REVIEW_OFFLINE_CANDIDATE: 6,
            self.REVIEW_PRESENTATION_CONFLICT: 7,
            self.PENDING_ECOMM_CATALOG: 8,
            self.INVALID_GTIN: 9,
        }
        items.sort(
            key=lambda item: (
                order.get(item["status"], 9),
                str(item.get("title") or "").casefold(),
                str(item.get("external_id") or ""),
            )
        )

        return {
            "available": True,
            "message": None,
            "summary": {
                "total_publications": len(edima),
                "linked": linked,
                "unlinked": unlinked,
                "ready_to_link": status_counts[self.READY_TO_LINK],
                "confirmed_by_human": confirmed_by_human,
                "review_required": unlinked - status_counts[self.READY_TO_LINK],
                "no_ecomm_match": status_counts[self.NO_ECOMM_MATCH],
                "invalid_gtin": status_counts[self.INVALID_GTIN],
                "ambiguous": status_counts[self.REVIEW_AMBIGUOUS],
                "multiple_gtin": status_counts[self.REVIEW_MULTIPLE_GTIN],
                "identifier_conflict": status_counts[self.REVIEW_IDENTIFIER_CONFLICT],
                "title_candidates": status_counts[self.REVIEW_TITLE_CANDIDATE],
                "offline_candidates": status_counts[self.REVIEW_OFFLINE_CANDIDATE],
                "presentation_conflict": status_counts[self.REVIEW_PRESENTATION_CONFLICT],
                "pending_ecomm_catalog": status_counts[self.PENDING_ECOMM_CATALOG],
                "distinct_unlinked_gtins": len(unlinked_gtins),
                "data_quality_invalid_gtin_total": invalid_gtin_total,
                "data_quality_multiple_gtin_total": multiple_gtin_total,
            },
            "policy": {
                "mode": "READ_ONLY_EDIMA_RECONCILIATION",
                "description": (
                    "KIKI Tech cruza el estado de vinculación informado por EDIMA con el catálogo "
                    "canónico de Ecomm-App usando primero el MLA exacto ya resuelto por la última "
                    "conciliación, luego el MLA guardado en las filas Ecomm y, como respaldo, el GTIN "
                    "exacto. Si los identificadores no alcanzan, el título se usa solo para sugerir "
                    "un candidato de revisión. También puede usar evidencia offline importada para "
                    "proponer candidatos históricos, siempre con confirmación humana. No modifica "
                    "Ecomm-App ni Mercado Libre."
                ),
                "safe_match": (
                    "Una publicación queda Lista para vincular cuando EDIMA indica No, contiene un "
                    "único GTIN válido y podemos identificar un único producto Ecomm por el MLA que "
                    "KIKI ya concilió, por un MLA directo en Ecomm o por GTIN exacto. Si MLA y GTIN se "
                    "contradicen, KIKI la manda a revisión. Los candidatos encontrados por título o "
                    "por evidencia offline solo pueden pasar a Lista para vincular después de una "
                    "confirmación humana."
                ),
            },
            "items": items,
        }

    def search_candidates(
        self,
        external_id: str,
        search: str = "",
        limit: int = 8,
    ) -> dict:
        external_id = str(external_id or "").strip()
        limit = max(1, min(int(limit or 8), 20))
        edima = self.repo.snapshot("EDIMA_LINKAGE")
        products = self.repo.snapshot("ECOMM_APP")
        row = next(
            (
                candidate
                for candidate in edima
                if str(candidate.get("external_id") or "").strip() == external_id
            ),
            None,
        )
        if not row:
            raise ValueError("La publicación EDIMA ya no está disponible.")
        if self._is_linked(row.get("inventory_linked")):
            raise ValueError("La publicación ya figura vinculada en EDIMA.")

        raw_search = str(search or "").strip()
        normalized_search = normalize_title(raw_search)
        target_title = normalize_title(row.get("title"))
        target_brand = normalize_title(row.get("brand"))
        target_gtins = {
            str(value).strip()
            for value in row.get("gtins") or []
            if str(value).strip()
        }

        scored = []
        for product in products:
            name = str(product.get("name") or "").strip()
            brand = str(product.get("brand") or "").strip()
            sku = str(product.get("sku_effective") or product.get("sku") or "").strip()
            ecomm_id = str(product.get("ecomm_id") or "").strip()
            eans = {
                str(value).strip()
                for value in [product.get("ean"), *(product.get("ean_aliases") or [])]
                if str(value or "").strip()
            }
            name_norm = normalize_title(name)
            brand_norm = normalize_title(brand)
            haystack = normalize_title(
                " ".join(
                    [
                        ecomm_id,
                        sku,
                        name,
                        brand,
                        " ".join(sorted(eans)),
                    ]
                )
            )

            reasons = []
            score = 0.0
            if raw_search:
                raw_cf = raw_search.casefold()
                exact_identifier = (
                    raw_cf == ecomm_id.casefold()
                    or raw_cf == sku.casefold()
                    or raw_search in eans
                )
                if exact_identifier:
                    score = 1.0
                    reasons.append("Identificador exacto")
                elif normalized_search and normalized_search in haystack:
                    score = 0.86
                    reasons.append("Coincide con tu búsqueda")
                elif normalized_search and name_norm:
                    similarity = SequenceMatcher(None, normalized_search, name_norm).ratio()
                    if similarity < 0.55:
                        continue
                    score = similarity
                    reasons.append(f"Nombre similar {similarity:.0%}")
                else:
                    continue
            else:
                if self._product_identity_conflict(row.get("title"), name):
                    continue
                if target_brand:
                    brand_in_name = bool(name_norm and target_brand in name_norm)
                    if brand_norm and target_brand != brand_norm:
                        continue
                    if not brand_norm and not brand_in_name:
                        continue

                similarity = (
                    SequenceMatcher(None, target_title, name_norm).ratio()
                    if target_title and name_norm
                    else 0.0
                )
                score = similarity
                if similarity:
                    reasons.append(f"Nombre similar {similarity:.0%}")
                if target_brand and (
                    target_brand == brand_norm
                    or (name_norm and target_brand in name_norm)
                ):
                    score += 0.15
                    reasons.append("Misma marca")
                if target_gtins and eans.intersection(target_gtins):
                    score = max(score, 1.0)
                    reasons.append("GTIN exacto")
                if score < 0.68:
                    continue

            product_issue = self._product_identity_conflict(row.get("title"), name)
            if product_issue and raw_search:
                reasons.append("⚠ " + product_issue)
                score = min(score, 0.35)

            scored.append(
                {
                    **self._product_view(product),
                    "score": min(score, 1.0),
                    "reasons": reasons,
                }
            )

        scored.sort(
            key=lambda item: (
                -float(item.get("score") or 0),
                str(item.get("name") or "").casefold(),
            )
        )
        return {
            "external_id": external_id,
            "title": row.get("title"),
            "brand": row.get("brand"),
            "gtin_raw": row.get("gtin_raw"),
            "search": raw_search,
            "candidates": scored[:limit],
        }

    def save_manual_assignment(
        self,
        external_id: str,
        ecomm_id: str,
        note: str | None = None,
    ) -> dict:
        external_id = str(external_id or "").strip()
        ecomm_id = str(ecomm_id or "").strip()
        if not external_id or not ecomm_id:
            raise ValueError("La publicación ML y el producto Ecomm son obligatorios.")

        edima = self.repo.snapshot("EDIMA_LINKAGE")
        products = self.repo.snapshot("ECOMM_APP")
        row = next(
            (
                candidate
                for candidate in edima
                if str(candidate.get("external_id") or "").strip() == external_id
            ),
            None,
        )
        if not row:
            raise ValueError("La publicación EDIMA ya no está disponible.")
        if self._is_linked(row.get("inventory_linked")):
            raise ValueError("La publicación ya figura vinculada en EDIMA.")

        current = self._decision_candidate(external_id)
        if current.get("status") not in {
            self.NO_ECOMM_MATCH,
            self.REVIEW_TITLE_CANDIDATE,
            self.REVIEW_OFFLINE_CANDIDATE,
        }:
            raise ValueError(
                "Esta publicación tiene un conflicto de identificadores que debe resolverse antes de asignarla manualmente."
            )

        product = next(
            (
                candidate
                for candidate in products
                if str(candidate.get("ecomm_id") or "").strip() == ecomm_id
            ),
            None,
        )
        if not product:
            raise ValueError("El producto Ecomm seleccionado ya no está disponible.")

        product_issue = self._product_identity_conflict(
            row.get("title"),
            product.get("name"),
        )
        if product_issue:
            raise ValueError(product_issue)

        now = datetime.now(timezone.utc)
        product_view = self._product_view(product)
        source_snapshot = {
            "title": row.get("title"),
            "gtin_raw": row.get("gtin_raw"),
            "matched_ecomm_id": ecomm_id,
            "match_method": "MANUAL_SEARCH",
        }
        history_entry = {
            "at": now.isoformat(),
            "decision": "CONFIRMED",
            "ecomm_id": ecomm_id,
            "note": note,
            "source_snapshot": source_snapshot,
        }
        decision = (
            self.db.query(InventoryLinkageDecision)
            .filter(InventoryLinkageDecision.external_id == external_id)
            .one_or_none()
        )
        if decision is None:
            decision = InventoryLinkageDecision(
                external_id=external_id,
                decision="CONFIRMED",
                ecomm_id=ecomm_id,
                source_snapshot=source_snapshot,
                product_snapshot=product_view,
                note=note,
                history=[history_entry],
                created_at=now,
                updated_at=now,
            )
            self.db.add(decision)
        else:
            history = list(decision.history or [])
            history.append(history_entry)
            decision.decision = "CONFIRMED"
            decision.ecomm_id = ecomm_id
            decision.source_snapshot = source_snapshot
            decision.product_snapshot = product_view
            decision.note = note
            decision.history = history[-100:]
            decision.updated_at = now

        self.db.commit()
        return {
            "external_id": row.get("external_id"),
            "variation_id": row.get("variation_id"),
            "title": row.get("title"),
            "brand": row.get("brand"),
            "gtin_raw": row.get("gtin_raw"),
            "gtins": [
                str(value).strip()
                for value in row.get("gtins") or []
                if str(value).strip()
            ],
            "inventory_linked": row.get("inventory_linked"),
            "modified_at": row.get("modified_at"),
            "status": self.READY_TO_LINK,
            "reason": (
                "Producto Ecomm elegido y confirmado manualmente dentro de KIKI Tech. "
                "La publicación queda lista para el siguiente paso de vinculación asistida."
            ),
            "match_method": "HUMAN_CONFIRMED_MANUAL",
            "offline_evidence": None,
            "decision_status": "CONFIRMED",
            "decision_note": note,
            "decision_at": now.isoformat(),
            "decision_source": "HUMAN_KIKI",
            "matched_product": product_view,
        }

    def mark_pending_ecomm_catalog(
        self,
        external_id: str,
        note: str | None = None,
    ) -> dict:
        external_id = str(external_id or "").strip()
        if not external_id:
            raise ValueError("La publicación ML es obligatoria.")

        item = self._decision_candidate(external_id)
        if item.get("status") != self.NO_ECOMM_MATCH:
            raise ValueError(
                "Solo se puede enviar a catálogo Ecomm una publicación que siga sin coincidencia."
            )

        now = datetime.now(timezone.utc)
        source_snapshot = {
            "title": item.get("title"),
            "gtin_raw": item.get("gtin_raw"),
            "matched_ecomm_id": None,
            "match_method": "NO_ECOMM_PRODUCT",
        }
        history_entry = {
            "at": now.isoformat(),
            "decision": "NO_ECOMM_PRODUCT",
            "ecomm_id": None,
            "note": note,
            "source_snapshot": source_snapshot,
        }
        row = (
            self.db.query(InventoryLinkageDecision)
            .filter(InventoryLinkageDecision.external_id == external_id)
            .one_or_none()
        )
        if row is None:
            row = InventoryLinkageDecision(
                external_id=external_id,
                decision="NO_ECOMM_PRODUCT",
                ecomm_id=None,
                source_snapshot=source_snapshot,
                product_snapshot={},
                note=note,
                history=[history_entry],
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
        else:
            history = list(row.history or [])
            history.append(history_entry)
            row.decision = "NO_ECOMM_PRODUCT"
            row.ecomm_id = None
            row.source_snapshot = source_snapshot
            row.product_snapshot = {}
            row.note = note
            row.history = history[-100:]
            row.updated_at = now

        self.db.commit()

        item = dict(item)
        item["status"] = self.PENDING_ECOMM_CATALOG
        item["reason"] = (
            "Revisado humanamente: no se encontró una coincidencia válida en el catálogo Ecomm "
            "actual. Requiere alta/corrección en Ecomm o importar un inventario más nuevo."
        )
        item["match_method"] = "HUMAN_NO_ECOMM_MATCH"
        item["decision_status"] = "PENDING_ECOMM"
        item["decision_note"] = note
        item["decision_at"] = now.isoformat()
        item["decision_source"] = "HUMAN_KIKI"
        item["matched_product"] = None
        return item

    def save_decision(
        self,
        external_id: str,
        decision_value: str,
        ecomm_id: str,
        note: str | None = None,
    ) -> dict:
        external_id = str(external_id or "").strip()
        ecomm_id = str(ecomm_id or "").strip()
        decision_value = str(decision_value or "").strip().upper()
        if decision_value not in {"CONFIRMED", "REJECTED"}:
            raise ValueError("La decisión debe ser CONFIRMED o REJECTED.")
        if not external_id or not ecomm_id:
            raise ValueError("La publicación ML y el producto Ecomm son obligatorios.")

        item = self._decision_candidate(external_id)
        if item.get("status") not in {
            self.REVIEW_TITLE_CANDIDATE,
            self.REVIEW_OFFLINE_CANDIDATE,
        }:
            raise ValueError(
                "Solo se pueden confirmar o rechazar candidatos sugeridos para revisión."
            )
        matched = item.get("matched_product") or {}
        if str(matched.get("ecomm_id") or "") != ecomm_id:
            raise ValueError("El producto Ecomm sugerido cambió; revisá nuevamente la fila.")
        product_issue = self._product_identity_conflict(
            item.get("title"),
            matched.get("name"),
        )
        if product_issue:
            raise ValueError(product_issue)

        now = datetime.now(timezone.utc)
        row = (
            self.db.query(InventoryLinkageDecision)
            .filter(InventoryLinkageDecision.external_id == external_id)
            .one_or_none()
        )
        source_snapshot = {
            "title": item.get("title"),
            "gtin_raw": item.get("gtin_raw"),
            "matched_ecomm_id": ecomm_id,
            "match_method": item.get("match_method"),
        }
        history_entry = {
            "at": now.isoformat(),
            "decision": decision_value,
            "ecomm_id": ecomm_id,
            "note": note,
            "source_snapshot": source_snapshot,
        }
        if row is None:
            row = InventoryLinkageDecision(
                external_id=external_id,
                decision=decision_value,
                ecomm_id=ecomm_id,
                source_snapshot=source_snapshot,
                product_snapshot=matched,
                note=note,
                history=[history_entry],
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
        else:
            history = list(row.history or [])
            history.append(history_entry)
            row.decision = decision_value
            row.ecomm_id = ecomm_id
            row.source_snapshot = source_snapshot
            row.product_snapshot = matched
            row.note = note
            row.history = history[-100:]
            row.updated_at = now

        self.db.commit()

        item = dict(item)
        item["decision_status"] = decision_value
        item["decision_note"] = note
        item["decision_at"] = now.isoformat()
        item["decision_source"] = "HUMAN_KIKI"
        if decision_value == "CONFIRMED":
            item["status"] = self.READY_TO_LINK
            item["match_method"] = (
                "HUMAN_CONFIRMED_OFFLINE"
                if str(item.get("match_method") or "").startswith("OFFLINE_")
                else "HUMAN_CONFIRMED_TITLE"
            )
            item["reason"] = (
                "Coincidencia confirmada humanamente dentro de KIKI Tech. "
                "La publicación queda lista para el siguiente paso de vinculación asistida."
            )
        else:
            item["reason"] = (
                "El candidato sugerido fue rechazado humanamente. "
                "La publicación sigue requiriendo identificación."
            )
        return item

    def _decision_candidate(self, external_id: str) -> dict:
        edima = self.repo.snapshot("EDIMA_LINKAGE")
        products = self.repo.snapshot("ECOMM_APP")
        offline_evidence = self.repo.snapshot("OFFLINE_LINKAGE_EVIDENCE")
        row = next(
            (
                candidate
                for candidate in edima
                if str(candidate.get("external_id") or "").strip() == external_id
            ),
            None,
        )
        if not row:
            raise ValueError("La publicación EDIMA ya no está disponible.")
        if self._is_linked(row.get("inventory_linked")):
            raise ValueError("La publicación ya figura vinculada en EDIMA.")

        product_by_ecomm_id = {
            str(product.get("ecomm_id") or "").strip(): product
            for product in products
            if str(product.get("ecomm_id") or "").strip()
        }
        offline_by_mla = {
            str(candidate.get("external_id") or "").strip(): candidate
            for candidate in offline_evidence
            if str(candidate.get("external_id") or "").strip()
        }

        ean_index: dict[str, list[dict]] = defaultdict(list)
        listing_index: dict[str, list[dict]] = defaultdict(list)
        title_index: dict[str, list[dict]] = defaultdict(list)
        normalized_products: list[tuple[dict, str]] = []
        for product in products:
            seen = set()
            for ean in [product.get("ean"), *(product.get("ean_aliases") or [])]:
                value = str(ean or "").strip()
                if value and value not in seen:
                    ean_index[value].append(product)
                    seen.add(value)
            listing_seen = set()
            for ecomm_row in product.get("ecomm_rows") or []:
                for raw_id in [ecomm_row.get("listing_id"), ecomm_row.get("marketplace_id")]:
                    for key in self._listing_keys(raw_id):
                        if key not in listing_seen:
                            listing_index[key].append(product)
                            listing_seen.add(key)
            normalized = normalize_title(product.get("name"))
            if normalized:
                title_index[normalized].append(product)
                normalized_products.append((product, normalized))

        reconciliation_index: dict[str, list[dict]] = defaultdict(list)
        latest_run = self.repo.latest_run()
        if latest_run:
            for result in latest_run.results or []:
                product = result.get("product")
                if not product:
                    continue
                raw_ids = list(result.get("matched_listing_ids") or [])
                listing = result.get("listing") or {}
                if listing.get("external_id"):
                    raw_ids.append(listing.get("external_id"))
                for raw_id in raw_ids:
                    for key in self._listing_keys(raw_id):
                        reconciliation_index[key].append(product)

        gtins = [
            str(value).strip()
            for value in row.get("gtins") or []
            if str(value).strip()
        ]
        valid_gtins = [value for value in gtins if self._valid_gtin(value)]
        status, reason, matched, match_method = self._classify_unlinked(
            row,
            gtins,
            valid_gtins,
            ean_index,
            listing_index,
            reconciliation_index,
            title_index,
            normalized_products,
        )
        offline_item = offline_by_mla.get(external_id)
        if status == self.NO_ECOMM_MATCH and offline_item:
            offline_candidate = product_by_ecomm_id.get(
                str(offline_item.get("candidate_ecomm_id") or "").strip()
            )
            if offline_candidate:
                matched = offline_candidate
                status = self.REVIEW_OFFLINE_CANDIDATE
                evidence_type = str(offline_item.get("evidence_type") or "").strip()
                match_method = f"OFFLINE_{evidence_type or 'REFERENCE'}"
                reason = (
                    "El documento de control offline propone este producto Ecomm como candidato. "
                    "Requiere confirmación humana antes de usarlo para vinculación."
                )

        return {
            "external_id": row.get("external_id"),
            "variation_id": row.get("variation_id"),
            "title": row.get("title"),
            "brand": row.get("brand"),
            "gtin_raw": row.get("gtin_raw"),
            "gtins": gtins,
            "inventory_linked": row.get("inventory_linked"),
            "modified_at": row.get("modified_at"),
            "status": status,
            "reason": reason,
            "match_method": match_method,
            "offline_evidence": offline_item or None,
            "decision_status": "NONE",
            "decision_note": None,
            "decision_at": None,
            "decision_source": "AUTOMATIC_IDENTIFIERS" if status == self.READY_TO_LINK else "NONE",
            "matched_product": self._product_view(matched) if matched else None,
        }

    @staticmethod
    def _decision_state(
        decision: InventoryLinkageDecision,
        row: dict,
        matched: dict,
    ) -> str:
        snapshot = decision.source_snapshot or {}
        current = {
            "title": row.get("title"),
            "gtin_raw": row.get("gtin_raw"),
            "matched_ecomm_id": str(matched.get("ecomm_id") or ""),
        }
        if (
            str(snapshot.get("title") or "") != str(current["title"] or "")
            or str(snapshot.get("gtin_raw") or "") != str(current["gtin_raw"] or "")
            or str(snapshot.get("matched_ecomm_id") or "")
            != current["matched_ecomm_id"]
        ):
            return "STALE"
        return decision.decision if decision.decision in {"CONFIRMED", "REJECTED"} else "STALE"

    def _classify_unlinked(
        self,
        row: dict,
        gtins: list[str],
        valid_gtins: list[str],
        ean_index,
        listing_index,
        reconciliation_index,
        title_index,
        normalized_products,
    ):
        if not gtins or not valid_gtins:
            return (
                self.INVALID_GTIN,
                "La publicación no tiene un GTIN utilizable para identificar el producto con seguridad.",
                None,
                "NONE",
            )
        if len(gtins) > 1:
            return (
                self.REVIEW_MULTIPLE_GTIN,
                "EDIMA informa más de un código de barras; requiere revisión antes de vincular.",
                None,
                "MULTIPLE_GTIN",
            )

        gtin = valid_gtins[0]
        listing_keys = self._listing_keys(row.get("external_id"))
        reconciliation_matches = self._unique_products(
            product
            for key in listing_keys
            for product in reconciliation_index.get(key, [])
        )
        raw_ecomm_matches = self._unique_products(
            product
            for key in listing_keys
            for product in listing_index.get(key, [])
        )
        mla_matches = reconciliation_matches or raw_ecomm_matches
        mla_source = (
            "RECONCILIATION_MLA"
            if reconciliation_matches
            else "ECOMM_MLA"
            if raw_ecomm_matches
            else None
        )
        ean_matches = self._unique_products(ean_index.get(gtin, []))

        if len(mla_matches) > 1:
            return (
                self.REVIEW_AMBIGUOUS,
                f"La publicación {row.get('external_id') or 'ML'} aparece asociada a más de un producto Ecomm.",
                None,
                f"{mla_source}_AMBIGUOUS" if mla_source else "MLA_AMBIGUOUS",
            )

        if len(mla_matches) == 1:
            matched = mla_matches[0]
            known_eans = {
                str(value).strip()
                for value in [matched.get("ean"), *(matched.get("ean_aliases") or [])]
                if str(value or "").strip()
            }
            if known_eans and gtin not in known_eans:
                return (
                    self.REVIEW_IDENTIFIER_CONFLICT,
                    f"El MLA coincide con un producto Ecomm, pero EDIMA informa GTIN {gtin} y el producto tiene otro EAN/GTIN.",
                    matched,
                    f"{mla_source}_GTIN_CONFLICT" if mla_source else "MLA_GTIN_CONFLICT",
                )
            if len(ean_matches) > 1:
                return (
                    self.REVIEW_AMBIGUOUS,
                    f"El MLA coincide con un producto Ecomm, pero el GTIN {gtin} aparece en más de un producto canónico.",
                    matched,
                    f"{mla_source}_GTIN_AMBIGUOUS" if mla_source else "MLA_GTIN_AMBIGUOUS",
                )
            if len(ean_matches) == 1 and ean_matches[0] is not matched:
                return (
                    self.REVIEW_IDENTIFIER_CONFLICT,
                    f"El MLA coincide con un producto Ecomm, pero el GTIN {gtin} identifica otro producto canónico.",
                    matched,
                    f"{mla_source}_GTIN_CONFLICT" if mla_source else "MLA_GTIN_CONFLICT",
                )
            return (
                self.READY_TO_LINK,
                f"MLA {row.get('external_id')} coincide exactamente con un único producto Ecomm; GTIN {gtin} queda como evidencia del vínculo.",
                matched,
                mla_source or "MLA_EXACT",
            )

        if len(ean_matches) == 1:
            return (
                self.READY_TO_LINK,
                f"GTIN {gtin} coincide exactamente con un único producto de Ecomm-App.",
                ean_matches[0],
                "GTIN_EXACT",
            )
        if len(ean_matches) > 1:
            return (
                self.REVIEW_AMBIGUOUS,
                f"GTIN {gtin} pertenece a más de un producto canónico de Ecomm-App.",
                None,
                "GTIN_AMBIGUOUS",
            )
        title_match = self._title_match(row, title_index, normalized_products)
        if title_match:
            matched, method, confidence = title_match
            known_eans = {
                str(value).strip()
                for value in [matched.get("ean"), *(matched.get("ean_aliases") or [])]
                if str(value or "").strip()
            }
            if known_eans and gtin not in known_eans:
                return (
                    self.REVIEW_IDENTIFIER_CONFLICT,
                    f"El título sugiere un producto Ecomm, pero EDIMA informa GTIN {gtin} y ese producto tiene otro EAN/GTIN.",
                    matched,
                    f"{method}_GTIN_CONFLICT",
                )
            return (
                self.REVIEW_TITLE_CANDIDATE,
                f"No hubo match por MLA/GTIN. El título sugiere un único producto Ecomm con {confidence:.0%} de similitud; requiere confirmación humana.",
                matched,
                method,
            )
        return (
            self.NO_ECOMM_MATCH,
            f"Ni el MLA {row.get('external_id') or '—'}, ni el GTIN {gtin}, ni el título identificaron un producto Ecomm con suficiente seguridad.",
            None,
            "NONE",
        )

    @classmethod
    def _title_match(cls, row: dict, title_index, normalized_products):
        title = normalize_title(row.get("title"))
        if not title:
            return None

        exact = cls._brand_compatible(row, title_index.get(title, []))
        if len(exact) == 1:
            return exact[0], "TITLE_EXACT", 1.0
        if len(exact) > 1:
            return None

        scored = []
        for product, candidate_title in normalized_products:
            if not cls._brand_compatible(row, [product]):
                continue
            score = SequenceMatcher(None, title, candidate_title).ratio()
            if score >= 0.90:
                scored.append((score, product))
        if not scored:
            return None
        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best_product = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        if best_score < 0.94 or best_score - second_score < 0.05:
            return None
        return best_product, "TITLE_HIGH_CONFIDENCE", best_score

    @staticmethod
    def _brand_compatible(row: dict, products: list[dict]) -> list[dict]:
        edima_brand = normalize_title(row.get("brand"))
        result = []
        for product in products:
            product_brand = normalize_title(product.get("brand"))
            if edima_brand and product_brand and edima_brand != product_brand:
                continue
            result.append(product)
        return result

    @classmethod
    def _product_identity_conflict(cls, source_title, candidate_title) -> str | None:
        presentation = cls._presentation_conflict(source_title, candidate_title)
        if presentation:
            return presentation
        return cls._variant_conflict(source_title, candidate_title)

    @classmethod
    def _variant_conflict(cls, source_title, candidate_title) -> str | None:
        source = normalize_title(source_title) or ""
        candidate = normalize_title(candidate_title) or ""
        if not source or not candidate:
            return None

        variants = [
            "SIN SABOR",
            "CLASICO",
            "ORIGINAL",
            "AVELLANA",
            "VAINILLA",
            "CHOCOLATE",
            "CARAMELO",
            "NEUTRO",
            "FRUTILLA",
        ]
        source_variants = [variant for variant in variants if variant in source]
        candidate_variants = [variant for variant in variants if variant in candidate]
        if source_variants and candidate_variants and set(source_variants) != set(candidate_variants):
            return (
                "La variante/sabor no coincide: "
                f"{', '.join(source_variants)} en la publicación vs "
                f"{', '.join(candidate_variants)} en Ecomm."
            )
        return None

    @classmethod
    def _presentation_conflict(cls, source_title, candidate_title) -> str | None:
        source = normalize_title(source_title) or ""
        candidate = normalize_title(candidate_title) or ""
        if not source or not candidate:
            return None

        source_pack = cls._pack_count(source)
        candidate_pack = cls._pack_count(candidate)
        if source_pack and source_pack > 1 and (candidate_pack or 1) != source_pack:
            return (
                f"La publicación es PACK X{source_pack}, pero el producto Ecomm seleccionado "
                "no tiene la misma presentación. Buscá un combo/SKU específico."
            )
        if candidate_pack and candidate_pack > 1 and (source_pack or 1) != candidate_pack:
            return (
                f"El producto Ecomm es PACK X{candidate_pack}, pero la publicación no tiene "
                "la misma presentación."
            )

        source_quantities = cls._quantities(source)
        candidate_quantities = cls._quantities(candidate)
        for dimension in set(source_quantities).intersection(candidate_quantities):
            if source_quantities[dimension] != candidate_quantities[dimension]:
                return (
                    "La presentación no coincide: "
                    f"{cls._format_quantity(dimension, source_quantities[dimension])} en la publicación "
                    f"vs {cls._format_quantity(dimension, candidate_quantities[dimension])} en Ecomm."
                )
        return None

    @staticmethod
    def _pack_count(normalized_title: str) -> int | None:
        match = re.search(r"\bPACK(?:\s+DE)?\s+X?\s*(\d+)\b", normalized_title)
        return int(match.group(1)) if match else None

    @staticmethod
    def _quantities(normalized_title: str) -> dict[str, int]:
        result: dict[str, int] = {}
        unit_map = {
            "ML": ("VOLUME_ML", 1),
            "CC": ("VOLUME_ML", 1),
            "L": ("VOLUME_ML", 1000),
            "LT": ("VOLUME_ML", 1000),
            "LTS": ("VOLUME_ML", 1000),
            "G": ("WEIGHT_G", 1),
            "GR": ("WEIGHT_G", 1),
            "GRS": ("WEIGHT_G", 1),
            "KG": ("WEIGHT_G", 1000),
            "CAP": ("COUNT_CAPS", 1),
            "CAPS": ("COUNT_CAPS", 1),
            "CAPSULA": ("COUNT_CAPS", 1),
            "CAPSULAS": ("COUNT_CAPS", 1),
        }
        for value, unit in re.findall(
            r"\b(\d+)\s*(ML|CC|LTS|LT|L|GRS|GR|G|KG|CAPSULAS|CAPSULA|CAPS|CAP)\b",
            normalized_title,
        ):
            dimension, multiplier = unit_map[unit]
            result[dimension] = int(value) * multiplier
        return result

    @staticmethod
    def _format_quantity(dimension: str, value: int) -> str:
        if dimension == "VOLUME_ML":
            return f"{value} ml"
        if dimension == "WEIGHT_G":
            return f"{value} g"
        if dimension == "COUNT_CAPS":
            return f"{value} cápsulas"
        return str(value)

    @staticmethod
    def _listing_keys(value) -> set[str]:
        text = str(value or "").strip().upper().replace(" ", "")
        if not text:
            return set()
        keys = {text}
        digits = "".join(char for char in text if char.isdigit())
        if digits:
            keys.add(digits)
            keys.add(f"MLA{digits}")
        return keys

    @staticmethod
    def _unique_products(products) -> list[dict]:
        result = []
        seen = set()
        for product in products:
            key = product.get("ecomm_id") or id(product)
            if key in seen:
                continue
            seen.add(key)
            result.append(product)
        return result

    @staticmethod
    def _product_view(product: dict) -> dict:
        return {
            "ecomm_id": product.get("ecomm_id"),
            "sku": product.get("sku_effective") or product.get("sku"),
            "name": product.get("name"),
            "brand": product.get("brand"),
            "ean": product.get("ean"),
            "stock": product.get("stock"),
        }

    @staticmethod
    def _is_linked(value) -> bool:
        return str(value or "").strip().casefold() in {"sí", "si", "yes"}

    @staticmethod
    def _valid_gtin(value: str) -> bool:
        if not value.isdigit() or len(value) not in {8, 12, 13, 14}:
            return False
        digits = [int(char) for char in value]
        total = 0
        for index, digit in enumerate(reversed(digits[:-1]), start=1):
            total += digit * (3 if index % 2 else 1)
        expected = (10 - total % 10) % 10
        return expected == digits[-1]

    @staticmethod
    def _unavailable(message: str) -> dict:
        return {
            "available": False,
            "message": message,
            "summary": {
                "total_publications": 0,
                "linked": 0,
                "unlinked": 0,
                "ready_to_link": 0,
                "confirmed_by_human": 0,
                "review_required": 0,
                "no_ecomm_match": 0,
                "invalid_gtin": 0,
                "ambiguous": 0,
                "multiple_gtin": 0,
                "identifier_conflict": 0,
                "title_candidates": 0,
                "offline_candidates": 0,
                "presentation_conflict": 0,
                "pending_ecomm_catalog": 0,
                "distinct_unlinked_gtins": 0,
                "data_quality_invalid_gtin_total": 0,
                "data_quality_multiple_gtin_total": 0,
            },
            "policy": {
                "mode": "READ_ONLY_EDIMA_RECONCILIATION",
                "description": "No hay datos suficientes para analizar la vinculación.",
                "safe_match": "",
            },
            "items": [],
        }
