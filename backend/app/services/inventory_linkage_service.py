from collections import Counter, defaultdict

from sqlalchemy.orm import Session

from ..repositories.catalog_repository import CatalogRepository


class InventoryLinkageService:
    """Cross EDIMA publication linkage state with canonical Ecomm products by GTIN."""

    READY_TO_LINK = "READY_TO_LINK"
    REVIEW_AMBIGUOUS = "REVIEW_AMBIGUOUS"
    REVIEW_MULTIPLE_GTIN = "REVIEW_MULTIPLE_GTIN"
    REVIEW_IDENTIFIER_CONFLICT = "REVIEW_IDENTIFIER_CONFLICT"
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
            self.INVALID_GTIN: 4,
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
                "distinct_unlinked_gtins": len(unlinked_gtins),
                "data_quality_invalid_gtin_total": invalid_gtin_total,
                "data_quality_multiple_gtin_total": multiple_gtin_total,
            },
            "policy": {
                "mode": "READ_ONLY_EDIMA_RECONCILIATION",
                "description": (
                    "KIKI Tech cruza el estado de vinculación informado por EDIMA con el catálogo "
                    "canónico de Ecomm-App usando GTIN exacto. No modifica Ecomm-App ni Mercado Libre."
                ),
                "safe_match": (
                    "Una publicación queda Lista para vincular solo cuando EDIMA indica No, contiene "
                    "un único GTIN válido y ese GTIN pertenece a un único producto canónico de Ecomm-App."
                ),
            },
            "items": items,
        }

    def _classify_unlinked(self, gtins: list[str], valid_gtins: list[str], ean_index):
        if not gtins or not valid_gtins:
            return (
                self.INVALID_GTIN,
                "La publicación no tiene un GTIN utilizable para identificar el producto con seguridad.",
                None,
            )
        if len(gtins) > 1:
            return (
                self.REVIEW_MULTIPLE_GTIN,
                "EDIMA informa más de un código de barras; requiere revisión antes de vincular.",
                None,
            )
        gtin = valid_gtins[0]
        matches = ean_index.get(gtin, [])
        if len(matches) == 1:
            return (
                self.READY_TO_LINK,
                f"GTIN {gtin} coincide exactamente con un único producto de Ecomm-App.",
                matches[0],
            )
        if len(matches) > 1:
            return (
                self.REVIEW_AMBIGUOUS,
                f"GTIN {gtin} pertenece a más de un producto canónico de Ecomm-App.",
                None,
            )
        return (
            self.NO_ECOMM_MATCH,
            f"GTIN {gtin} no se encontró en el catálogo canónico actual de Ecomm-App.",
            None,
        )

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
