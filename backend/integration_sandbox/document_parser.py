"""Compatibility import: one shared parser, no duplicated implementation."""
from document_reader.parser import *  # noqa: F403

from document_reader import parser as _shared

def __getattr__(name):
    return getattr(_shared, name)
