from app.services.documental.generation_contract import (
    generation_context as common_context,
)
from .proposals import Proposals


def generation_context(db, session, ident):
    return common_context(db, session, ident, Proposals)
