"""Pilot-only size profile. Shared bounded parser transport and document service."""

from app.services.documental.local_documents import (
    LocalDocuments as CommonLocalDocuments,
    parse_local as common_parse,
    public_body as public_body,
    valid_url as valid_url,
)
from .research.service import Research
from .research.storage import Document
from .hileret_brochure import MAX_REQUEST


def parse_local(body):
    return common_parse(body, max_request=MAX_REQUEST)


class LocalDocuments(CommonLocalDocuments):
    research_type = Research
    Document = Document
