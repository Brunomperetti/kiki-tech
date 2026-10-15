"""Deterministic dry-run of the planned AI review flow. No model calls or writes."""
from .tiendanube_enrichment_proposal_service import TiendanubeEnrichmentProposalService


class TiendanubeAiOfflinePreviewService:
    def __init__(self, db):
        self.proposals = TiendanubeEnrichmentProposalService(db)

    def preview(self, product_key: str):
        report = self.proposals.report()
        item = next((row for row in report["items"] if row["product_key"] == product_key), None)
        if item is None:
            raise ValueError("El producto no tiene una propuesta disponible.")
        missing = []
        if item["description_action"] == "RESEARCH_REQUIRED":
            missing.append("Consultar fuentes confiables antes de redactar la descripción.")
        return {
            "product_key": item["product_key"],
            "original_title": item["original_name"],
            "title": item["proposed_title"],
            "description": "",
            "questions": missing,
            "evidence": item["verified_product_facts"],
            "status": "OFFLINE_SIMULATION",
            "policy": "Simulación determinista, NO inteligencia artificial. No hubo llamadas pagas, guardado ni publicación.",
        }
