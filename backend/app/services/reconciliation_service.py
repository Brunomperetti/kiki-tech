import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..catalog.canonicalizer import EcommCanonicalizer
from ..catalog.models import ChannelListing, EcommChannelRow, Product
from ..catalog.reconciler import CatalogReconciler
from ..core.config import get_settings
from ..database.models import ImportJobRecord, ReconciliationRun
from ..integrations.ecomm_app.edima_linkage_importer import EdimaLinkageExcelImporter
from ..integrations.ecomm_app.excel_importer import EcommExcelImporter
from ..integrations.mercadolibre.excel_importer import MercadoLibreExcelImporter
from ..repositories.catalog_repository import CatalogRepository

logger = logging.getLogger(__name__)


class ReconciliationService:
    def __init__(self, db: Session):
        self.repo = CatalogRepository(db)

    def import_file(self, source: str, filename: str, content: bytes):
        if source == "ECOMM_APP":
            importer = EcommExcelImporter()
        elif source == "EDIMA_LINKAGE":
            importer = EdimaLinkageExcelImporter()
        else:
            importer = MercadoLibreExcelImporter()
        logger.info("import_started source=%s filename=%s", source, filename)
        report = importer.read(content)
        payload = [item.model_dump(mode="json") for item in report.records]
        diagnostics = {
            "rows_read": report.rows_read,
            "rows_accepted": report.rows_accepted,
            "rows_discarded": report.rows_discarded,
            "header_row": report.header_row,
            "recognized_columns": report.mapped_columns,
            "ignored_columns": report.unknown_columns,
            "warnings": report.warnings,
        }

        if source == "ECOMM_APP":
            canonical = EcommCanonicalizer().canonicalize(report.records)
            self.repo.save_snapshot("ECOMM_APP_RAW", payload)
            self.repo.save_snapshot(
                "ECOMM_APP",
                [product.model_dump(mode="json") for product in canonical.products],
            )
            diagnostics.update(
                canonical_products=len(canonical.products),
                grouped_rows=canonical.grouped_rows,
                associated_rows=canonical.associated_rows,
                conflicts=canonical.conflicts,
            )
            if canonical.conflicts:
                diagnostics["warnings"].append(
                    f"Se detectaron {len(canonical.conflicts)} conflictos de datos canónicos."
                )
        else:
            self.repo.save_snapshot(source, payload)

        job = self.repo.add_job(
            ImportJobRecord(
                source=source,
                filename=filename,
                records=report.rows_read,
                processed=report.rows_accepted,
                errors=report.rows_discarded,
                status="COMPLETED",
                unknown_columns=diagnostics,
                finished_at=datetime.now(timezone.utc),
            )
        )
        logger.info(
            "import_finished source=%s records=%d warnings=%d",
            source,
            len(payload),
            len(diagnostics["warnings"]),
        )
        return job

    def analyze(self, ml_source: str = "AUTO"):
        products = [
            Product.model_validate(item) for item in self.repo.snapshot("ECOMM_APP")
        ]
        raw_rows = [
            EcommChannelRow.model_validate(item)
            for item in self.repo.snapshot("ECOMM_APP_RAW")
        ]
        source = self._choose_ml_source(ml_source)
        listings = [
            ChannelListing.model_validate(item) for item in self.repo.snapshot(source)
        ]
        logger.info(
            "reconciliation_started products=%d listings=%d",
            len(products),
            len(listings),
        )
        results = CatalogReconciler().reconcile(products, listings)
        serialized = [result.model_dump(mode="json") for result in results]
        counts = Counter(result.status.value for result in results)
        associated_rows = sum(
            bool(row.marketplace or row.marketplace_id or row.store or row.listing_id)
            for row in raw_rows
        )
        summary = {
            "mercadolibre_source": source,
            "total_ecomm_rows": len(raw_rows),
            "total_products": len(products),
            "total_ecomm_associated_rows": associated_rows,
            "total_listings": len(listings),
            "MULTIPLE_ML_LISTINGS": sum(
                result.multiple_ml_listings for result in results if result.product
            ),
            **{
                key: counts.get(key, 0)
                for key in [
                    "ALREADY_PUBLISHED",
                    "CANDIDATE_TO_PUBLISH",
                    "REVIEW_REQUIRED",
                    "POSSIBLE_DUPLICATE",
                    "INCOMPLETE_DATA",
                    "INVALID_SKU",
                    "INVALID_EAN",
                    "UNMATCHED_ML_LISTING",
                ]
            },
        }
        run = self.repo.add_run(ReconciliationRun(results=serialized, summary=summary))
        logger.info("reconciliation_finished results=%d", len(results))
        return run

    def _choose_ml_source(self, requested: str) -> str:
        requested = requested.upper()
        if requested not in {"AUTO", "API", "XLSX"}:
            raise ValueError("La fuente debe ser AUTO, API o XLSX.")
        if requested == "XLSX":
            return "MERCADOLIBRE"
        api_snapshot = self.repo.snapshot_record("MERCADOLIBRE_API")
        if requested == "API":
            if not api_snapshot:
                raise ValueError("No existe un snapshot de Mercado Libre API.")
            return "MERCADOLIBRE_API"
        if api_snapshot:
            updated = api_snapshot.updated_at
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            max_age = timedelta(hours=get_settings().ml_snapshot_fresh_hours)
            if datetime.now(timezone.utc) - updated <= max_age:
                return "MERCADOLIBRE_API"
        return "MERCADOLIBRE"
