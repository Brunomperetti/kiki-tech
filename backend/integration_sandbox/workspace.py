"""Existing editor, with one explicit LOCAL reference; never changes API catalog."""

from app.services.ecomm_api_product_workspace_service import (
    EcommApiProductWorkspace as ExistingWorkspace,
)
from .mama_reference import PILOT_ID, source
from .research.storage import Dossier


class EcommApiProductWorkspace(ExistingWorkspace):
    def _source(self, ident):
        if ident != PILOT_ID:
            return super()._source(ident)
        if self.db.get(Dossier, PILOT_ID) is None:
            raise ValueError(
                "Prepará el expediente de pruebas MAMA antes de abrir su editor."
            )
        return source()

    def save(self, ecomm_id, fields, status, expected_version):
        if ecomm_id == PILOT_ID and status != "DRAFT":
            raise ValueError(
                "Ecomm ID real pendiente: este expediente sólo admite borradores de prueba, sin aprobación para canales."
            )
        return super().save(ecomm_id, fields, status, expected_version)
