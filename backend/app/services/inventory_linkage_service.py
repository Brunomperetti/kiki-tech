from collections import Counter, defaultdict
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from ..catalog.normalizer import normalize_title
from ..repositories.catalog_repository import CatalogRepository


class InventoryLinkageService:
    """Cross EDIMA publication linkage state with canonical Ecomm products by GTIN."""

    READY_TO_LINK = "READY_TO_LINK"
    REVIEW_AMBIGUOUS = "REVIEW_AMBIGUOUS"
    REVIEW_MULTIPLE_GTIN = "REVIEW_MULTIPLE_GTIN"
    REVIEW_IDENTIFIER_CONFLICT = "REVIEW_IDENTIFIER_CONFLICT"
    REVIEW_TITLE_CANDIDATE = "REVIEW_TITLE_CANDIDATE"
    INVALID_GTIN = "INVALID_GTIN"
    NO_ECOMM_MATCH = "NO_ECOMM_MATCH"

    def __init__(self, db: Session):
        self.repo = CatalogRepository(db)

    def report(self) -> dict:
        edima = self.repo.snapshot("EDIMA_LINKAGE")
        products = self.repo.snapshot("ECOMM_APP")
        if not edima:
            return self._unavailable(
                "Importá el reporte EDIMA de Mercado Libre para analizar la vinculación de inventario."
            )
        if not products:
            return self._unavailable(
                "Importá primero el catálogo de Ecomm-App para cruzar los GTIN de EDIMA."
            )

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
            self.INVALID_GTIN: 6,
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
                "review_required": unlinked - status_counts[self.READY_TO_LINK],
                "no_ecomm_match": status_counts[self.NO_ECOMM_MATCH],
                "invalid_gtin": status_counts[self.INVALID_GTIN],
                "ambiguous": status_counts[self.REVIEW_AMBIGUOUS],
                "multiple_gtin": status_counts[self.REVIEW_MULTIPLE_GTIN],
                "identifier_conflict": status_counts[self.REVIEW_IDENTIFIER_CONFLICT],
                "title_candidates": status_counts[self.REVIEW_TITLE_CANDIDATE],
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
                    "un candidato de revisión. No modifica Ecomm-App ni Mercado Libre."
                ),
                "safe_match": (
                    "Una publicación queda Lista para vincular cuando EDIMA indica No, contiene un "
                    "único GTIN válido y podemos identificar un único producto Ecomm por el MLA que "
                    "KIKI ya concilió, por un MLA directo en Ecomm o por GTIN exacto. Si MLA y GTIN se "
                    "contradicen, KIKI la manda a revisión."
                ),
            },
            "items": items,
        }

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
                "review_required": 0,
                "no_ecomm_match": 0,
                "invalid_gtin": 0,
                "ambiguous": 0,
                "multiple_gtin": 0,
                "identifier_conflict": 0,
                "title_candidates": 0,
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
