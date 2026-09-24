import logging
from collections import Counter
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from ..catalog.models import ChannelListing, Product
from ..catalog.reconciler import CatalogReconciler
from ..database.models import ImportJobRecord, ReconciliationRun
from ..integrations.ecomm_app.excel_importer import EcommExcelImporter
from ..integrations.mercadolibre.excel_importer import MercadoLibreExcelImporter
from ..repositories.catalog_repository import CatalogRepository
logger=logging.getLogger(__name__)
class ReconciliationService:
    def __init__(self, db: Session): self.repo=CatalogRepository(db)
    def import_file(self, source: str, filename: str, content: bytes):
        importer=EcommExcelImporter() if source=="ECOMM_APP" else MercadoLibreExcelImporter()
        logger.info("import_started source=%s filename=%s", source, filename)
        report=importer.read(content); payload=[x.model_dump(mode="json") for x in report.records]
        self.repo.save_snapshot(source,payload)
        diagnostics={"rows_read":report.rows_read,"rows_accepted":report.rows_accepted,"rows_discarded":report.rows_discarded,"header_row":report.header_row,"recognized_columns":report.mapped_columns,"ignored_columns":report.unknown_columns,"warnings":report.warnings}
        job=self.repo.add_job(ImportJobRecord(source=source,filename=filename,records=report.rows_read,processed=report.rows_accepted,errors=report.rows_discarded,status="COMPLETED",unknown_columns=diagnostics,finished_at=datetime.now(timezone.utc)))
        logger.info("import_finished source=%s records=%d warnings=%d",source,len(payload),len(report.unknown_columns)); return job
    def analyze(self):
        products=[Product.model_validate(x) for x in self.repo.snapshot("ECOMM_APP")]; listings=[ChannelListing.model_validate(x) for x in self.repo.snapshot("MERCADOLIBRE")]
        logger.info("reconciliation_started products=%d listings=%d",len(products),len(listings))
        results=CatalogReconciler().reconcile(products,listings); serialized=[x.model_dump(mode="json") for x in results]
        counts=Counter(x.status.value for x in results)
        summary={"total_products":len(products),"total_listings":len(listings),**{key:counts.get(key,0) for key in ["ALREADY_PUBLISHED","CANDIDATE_TO_PUBLISH","REVIEW_REQUIRED","POSSIBLE_DUPLICATE","INCOMPLETE_DATA","INVALID_SKU","INVALID_EAN","UNMATCHED_ML_LISTING"]}}
        run=self.repo.add_run(ReconciliationRun(results=serialized,summary=summary)); logger.info("reconciliation_finished results=%d",len(results)); return run
