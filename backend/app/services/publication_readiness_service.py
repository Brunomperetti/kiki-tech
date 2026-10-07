from collections import Counter, defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from ..database.duplicate_review import DuplicateReviewDecision
from ..database.reconciliation_review import ReconciliationReviewDecision
from ..repositories.catalog_repository import CatalogRepository
from .duplicate_review_service import DuplicateReviewService
from .reconciliation_review_service import ReconciliationReviewService


class PublicationReadinessService:
    """Classify reconciled Ecomm products before any future Mercado Libre write flow.

    READY_CORE_DATA means the product passed the checks that can be performed with the
    current Ecomm/XLSX + reconciliation data. It is intentionally not equivalent to
    "ready to publish": images, Mercado Libre category and category attributes still
    require validation later.
    """

    READY_CORE_DATA = "READY_CORE_DATA"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"
    EXCLUDED_BULK = "EXCLUDED_BULK"
    NO_STOCK = "NO_STOCK"
    ALREADY_PUBLISHED = "ALREADY_PUBLISHED"

    REASON_LABELS = {
        "EAN_MISSING": "Falta EAN/GTIN",
        "BRAND_MISSING": "Falta marca",
        "STOCK_MISSING": "Falta stock informado",
        "SKU_DUPLICATE": "SKU duplicado",
        "SKU_MISSING": "Falta SKU",
        "SKU_INVALID": "SKU inválido",
        "EAN_INVALID": "EAN inválido",
        "NAME_MISSING": "Falta nombre",
        "PRICE_INVALID": "Precio inválido",
        "STOCK_INVALID": "Stock inválido",
        "RECONCILIATION_REVIEW": "Conciliación requiere revisión",
        "DATA_ERROR": "Datos inconsistentes",
        "EAN_BASE_SKU_MISSING": "EAN sin SKU base único de 4 dígitos",
        "EAN_BASE_SKU_AMBIGUOUS": "EAN con más de un SKU base de 4 dígitos",
        "ASSOCIATED_SKU_OUT_OF_BULK": "SKU asociado / combo fuera del masivo actual",
        "NO_STOCK": "Sin stock",
        "ALREADY_PUBLISHED": "Ya publicado",
        "CORE_DATA_OK": "Datos centrales OK",
    }

    def __init__(self, db: Session):
        self.db = db
        self.repo = CatalogRepository(db)

    def report(self) -> dict:
        run = self.repo.latest_run()
        if not run:
            raise ValueError(
                "Primero ejecutá una reconciliación para preparar los candidatos de publicación."
            )

        reconciliation_decisions = {
            row.product_key: row
            for row in self.db.query(ReconciliationReviewDecision).all()
        }
        duplicate_rows = self.db.query(DuplicateReviewDecision).all()
        duplicate_decisions = DuplicateReviewService.product_decision_index(duplicate_rows)

        raw_results = run.results or []
        bulk_rules = self._bulk_rules(raw_results)
        items = []
        counts: Counter[str] = Counter()
        attention_reasons: Counter[str] = Counter()
        for index, raw_result in enumerate(raw_results):
            product = raw_result.get("product")
            if not product:
                continue

            original_status = raw_result.get("status")
            manual_decision = None
            manual_duplicate_decision = None
            result = dict(raw_result)
            result["bulk_rule"] = bulk_rules[index]

            if original_status == "REVIEW_REQUIRED":
                try:
                    key = ReconciliationReviewService.product_key(product)
                except ValueError:
                    key = None
                decision = reconciliation_decisions.get(key) if key else None
                if decision and decision.decision != ReconciliationReviewService.PENDING:
                    manual_decision = decision.decision
                    if decision.decision == ReconciliationReviewService.CONFIRMED_MATCH:
                        result["status"] = "ALREADY_PUBLISHED"
                        result["reason"] = "Coincidencia confirmada manualmente en KIKI Tech."
                    elif decision.decision == ReconciliationReviewService.NOT_MATCH:
                        result["status"] = "CANDIDATE_TO_PUBLISH"
                        result["reason"] = "Coincidencia descartada manualmente; se trata como candidato."

            if original_status == "POSSIBLE_DUPLICATE":
                try:
                    duplicate_key = DuplicateReviewService.product_key(product)
                except ValueError:
                    duplicate_key = None
                duplicate_decision = duplicate_decisions.get(duplicate_key) if duplicate_key else None
                if duplicate_decision:
                    manual_duplicate_decision = duplicate_decision.decision
                    if duplicate_decision.decision == DuplicateReviewService.DUPLICATE_CONFIRMED:
                        result["reason"] = (
                            "Duplicado confirmado manualmente; requiere corrección en el catálogo de origen."
                        )
                    elif duplicate_decision.decision in {
                        DuplicateReviewService.DISTINCT_PRODUCTS,
                        DuplicateReviewService.VARIANTS,
                    }:
                        result = DuplicateReviewService.reclassify_resolved_duplicate(result)
                        result["bulk_rule"] = bulk_rules[index]

            readiness_status, reasons = self.classify(result)
            reason_codes = self.reason_codes(result, readiness_status)
            counts[readiness_status] += 1
            if readiness_status in {self.REVIEW_REQUIRED, self.BLOCKED}:
                attention_reasons.update(reason_codes)
            items.append(
                {
                    "product": product,
                    "reconciliation_status": result.get("status"),
                    "original_reconciliation_status": original_status,
                    "manual_reconciliation_decision": manual_decision,
                    "manual_duplicate_decision": manual_duplicate_decision,
                    "readiness_status": readiness_status,
                    "reason_codes": reason_codes,
                    "reasons": reasons,
                    "issues": result.get("issues") or [],
                    "matched_listing_ids": result.get("matched_listing_ids") or [],
                    "bulk_rule": result.get("bulk_rule"),
                }
            )

        actionable = (
            counts[self.READY_CORE_DATA]
            + counts[self.REVIEW_REQUIRED]
            + counts[self.BLOCKED]
        )
        reason_summary = [
            {
                "code": code,
                "label": self.REASON_LABELS.get(code, code.replace("_", " ").title()),
                "count": count,
            }
            for code, count in attention_reasons.most_common()
        ]
        return {
            "reconciliation_run_id": run.id,
            "mercadolibre_source": (run.summary or {}).get("mercadolibre_source"),
            "summary": {
                "total_products": len(items),
                "actionable_with_stock": actionable,
                self.READY_CORE_DATA: counts[self.READY_CORE_DATA],
                self.REVIEW_REQUIRED: counts[self.REVIEW_REQUIRED],
                self.BLOCKED: counts[self.BLOCKED],
                self.EXCLUDED_BULK: counts[self.EXCLUDED_BULK],
                self.NO_STOCK: counts[self.NO_STOCK],
                self.ALREADY_PUBLISHED: counts[self.ALREADY_PUBLISHED],
            },
            "reason_summary": reason_summary,
            "bulk_policy": {
                "mode": "CURRENT_ML_BULK_RULE",
                "excluded_count": counts[self.EXCLUDED_BULK],
                "description": (
                    "Para el masivo actual, un SKU numérico de 5 o más dígitos asociado al mismo "
                    "EAN que un único SKU base de 4 dígitos se identifica como combo/asociado y no "
                    "avanza a publicación masiva. Si el EAN no tiene un único SKU base de 4 dígitos, "
                    "el caso requiere revisión."
                ),
            },
            "pending_external_checks": [
                "Imágenes disponibles y aptas para Mercado Libre",
                "Categoría de Mercado Libre",
                "Atributos obligatorios de la categoría",
            ],
            "items": items,
        }

    @classmethod
    def reason_codes(cls, result: dict, readiness_status: str) -> list[str]:
        bulk_rule = result.get("bulk_rule") or {}
        if readiness_status == cls.ALREADY_PUBLISHED:
            return ["ALREADY_PUBLISHED"]
        if readiness_status == cls.NO_STOCK:
            return ["NO_STOCK"]
        if readiness_status == cls.EXCLUDED_BULK:
            return [bulk_rule.get("reason_code") or "ASSOCIATED_SKU_OUT_OF_BULK"]
        if readiness_status == cls.READY_CORE_DATA:
            return ["CORE_DATA_OK"]

        product = result.get("product") or {}
        derived_codes = []
        if not product.get("ean"):
            derived_codes.append("EAN_MISSING")
        if not product.get("brand"):
            derived_codes.append("BRAND_MISSING")
        issue_codes = [
            issue.get("code")
            for issue in result.get("issues") or []
            if issue.get("code")
        ]
        if readiness_status == cls.BLOCKED and issue_codes:
            return list(dict.fromkeys(issue_codes))
        if bulk_rule.get("action") == "REVIEW":
            return [bulk_rule.get("reason_code") or "DATA_ERROR"]
        combined_codes = list(dict.fromkeys([*derived_codes, *issue_codes]))
        if combined_codes:
            return combined_codes
        if readiness_status == cls.REVIEW_REQUIRED:
            return ["RECONCILIATION_REVIEW"]
        return ["DATA_ERROR"]

    @classmethod
    def classify(cls, result: dict) -> tuple[str, list[str]]:
        status = result.get("status")
        product = result.get("product") or {}
        issues = result.get("issues") or []
        issue_codes = {issue.get("code") for issue in issues}
        issue_messages = [
            issue.get("message") for issue in issues if issue.get("message")
        ]

        if status == "ALREADY_PUBLISHED":
            return cls.ALREADY_PUBLISHED, ["Ya tiene una publicación asociada."]

        stock = cls._decimal(product.get("stock"))
        if stock is not None and stock <= 0:
            return cls.NO_STOCK, ["El producto no tiene stock disponible."]

        if status in {
            "POSSIBLE_DUPLICATE",
            "INVALID_SKU",
            "INVALID_EAN",
            "INCOMPLETE_DATA",
        }:
            return cls.BLOCKED, issue_messages or [
                "Tiene un error de datos que bloquea la preparación."
            ]

        if status == "REVIEW_REQUIRED":
            reason = result.get("reason")
            return cls.REVIEW_REQUIRED, [reason] if reason else issue_messages

        if status != "CANDIDATE_TO_PUBLISH":
            return cls.REVIEW_REQUIRED, [
                "El estado de conciliación requiere revisión antes de continuar."
            ]

        bulk_rule = result.get("bulk_rule") or {}
        if bulk_rule.get("action") == "EXCLUDE":
            return cls.EXCLUDED_BULK, [bulk_rule["message"]]
        if bulk_rule.get("action") == "REVIEW":
            return cls.REVIEW_REQUIRED, [bulk_rule["message"]]

        reasons: list[str] = []
        if stock is None:
            reasons.append("Falta stock informado.")
        if not product.get("ean") or "EAN_MISSING" in issue_codes:
            reasons.append("Falta EAN/GTIN; requiere revisión antes de publicar.")
        if not product.get("brand") or "BRAND_MISSING" in issue_codes:
            reasons.append("Falta marca; requiere revisión antes de publicar.")
        if reasons:
            return cls.REVIEW_REQUIRED, reasons

        return cls.READY_CORE_DATA, [
            "Datos centrales de Ecomm validados; faltan controles externos de imágenes, categoría y atributos."
        ]

    @classmethod
    def _bulk_rules(cls, results: list[dict]) -> list[dict | None]:
        """Build the current business-rule decision for each reconciled Ecomm product.

        Business rule supplied by KIKI: an EAN should have one numeric 4-digit base SKU.
        Numeric SKUs with 5+ digits under that EAN are associated SKUs / combos and are
        temporarily excluded from the new-publication bulk flow. No EAN-prefix rule is
        encoded here because that instruction still needs exact confirmation.
        """

        ean_to_skus: dict[str, set[str]] = defaultdict(set)
        products: list[dict] = []
        for raw_result in results:
            product = raw_result.get("product") or {}
            products.append(product)
            eans = cls._ean_values(product)
            skus = cls._sku_values(product)
            for ean in eans:
                for sku in skus:
                    if sku.isdigit():
                        ean_to_skus[ean].add(sku)

        rules: list[dict | None] = []
        for product in products:
            effective_sku = str(
                product.get("sku_effective") or product.get("sku") or ""
            ).strip()
            eans = cls._ean_values(product)
            if not effective_sku.isdigit() or not eans:
                rules.append(None)
                continue

            base_skus = sorted(
                {
                    sku
                    for ean in eans
                    for sku in ean_to_skus.get(ean, set())
                    if len(sku) == 4
                }
            )

            if len(base_skus) > 1:
                rules.append(
                    {
                        "action": "REVIEW",
                        "reason_code": "EAN_BASE_SKU_AMBIGUOUS",
                        "base_skus": base_skus,
                        "message": (
                            "El EAN está asociado a más de un SKU numérico de 4 dígitos "
                            f"({', '.join(base_skus)}). Hay que confirmar cuál es el SKU base único."
                        ),
                    }
                )
                continue

            if len(effective_sku) >= 5:
                if len(base_skus) == 1:
                    rules.append(
                        {
                            "action": "EXCLUDE",
                            "reason_code": "ASSOCIATED_SKU_OUT_OF_BULK",
                            "base_sku": base_skus[0],
                            "message": (
                                f"SKU {effective_sku} asociado al SKU base {base_skus[0]} para el "
                                "mismo EAN. Se considera combo/asociado y no entra al masivo "
                                "actual de nuevas publicaciones de Mercado Libre."
                            ),
                        }
                    )
                else:
                    rules.append(
                        {
                            "action": "REVIEW",
                            "reason_code": "EAN_BASE_SKU_MISSING",
                            "message": (
                                f"SKU {effective_sku} tiene 5 o más dígitos, pero para su EAN no "
                                "se encontró un SKU base único de 4 dígitos en Ecomm-App."
                            ),
                        }
                    )
                continue

            rules.append(None)

        return rules

    @staticmethod
    def _sku_values(product: dict) -> list[str]:
        values = [
            product.get("sku_effective"),
            product.get("sku"),
            product.get("sku_variant"),
            product.get("sku_product"),
            *(product.get("sku_aliases") or []),
        ]
        return list(
            dict.fromkeys(
                str(value).strip()
                for value in values
                if value is not None and str(value).strip()
            )
        )

    @staticmethod
    def _ean_values(product: dict) -> list[str]:
        values = [product.get("ean"), *(product.get("ean_aliases") or [])]
        return list(
            dict.fromkeys(
                str(value).strip()
                for value in values
                if value is not None and str(value).strip()
            )
        )

    @staticmethod
    def _decimal(value) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None
