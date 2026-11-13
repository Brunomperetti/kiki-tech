"""Existing editor, with one explicit LOCAL reference; never changes API catalog."""

from app.services.ecomm_api_product_workspace_service import (
    EcommApiProductWorkspace as ExistingWorkspace,
)
from .mama_reference import PILOT_ID, source
from .hileret_reference import PILOTS, source as hileret_source
from .research.storage import Dossier


class EcommApiProductWorkspace(ExistingWorkspace):
    def _source(self, ident):
        if ident in PILOTS:
            if self.db.get(Dossier, ident) is None:
                raise ValueError(
                    "Prepará el expediente Hileret de pruebas antes de abrir su editor."
                )
            return hileret_source(ident)
        if ident != PILOT_ID:
            return super()._source(ident)
        if self.db.get(Dossier, PILOT_ID) is None:
            raise ValueError(
                "Prepará el expediente de pruebas MAMA antes de abrir su editor."
            )
        return source()

    def save(self, ecomm_id, fields, status, expected_version):
        if (ecomm_id == PILOT_ID or ecomm_id in PILOTS) and status != "DRAFT":
            raise ValueError(
                "Ecomm ID real pendiente: este expediente sólo admite borradores de prueba, sin aprobación para canales."
            )
        return super().save(ecomm_id, fields, status, expected_version)
