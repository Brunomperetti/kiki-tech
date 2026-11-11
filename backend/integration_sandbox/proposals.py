"""Synthetic/pilot profile; proposal algorithms and editor persistence are shared."""

from app.services.documental.proposals import Proposals as CommonProposals
from .research.service import Research
from .workspace import EcommApiProductWorkspace

MODEL = "deterministic-synthetic-evidence-v1"
EVENT = "SYNTHETIC_EVIDENCE_PROPOSAL"


class Proposals(CommonProposals):
    research_type = Research
    workspace_type = EcommApiProductWorkspace
    model, event = MODEL, EVENT
    product_prefix = "ECOMM_API:"

    def before_generate(self, ident, facts):
        from .mama_reference import PILOT_ID
        from .hileret_reference import PILOTS

        if ident in PILOTS and not facts:
            raise ValueError(
                "Propuesta Hileret bloqueada: falta PDF original con procedencia revisada, identidad compatible y hechos aprobados. Excel, URL y datos comunicados no bastan. Unidad, pack x6 y caja x9 no son intercambiables."
            )
        if ident == PILOT_ID and not facts:
            raise ValueError(
                "Propuesta bloqueada: faltan documentos específicos con EAN, marca, ancho 10 mm y contenido neto 350 g, procedencia revisada y hechos aprobados. La URL candidata y el Excel informado no bastan."
            )
