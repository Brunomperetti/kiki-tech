"""Offline harness: same reader, kernel network=none supplied by Docker."""
from document_reader.worker import Handler, Server, child_guard, read_exact, serve  # noqa: F401

if __name__ == "__main__":
    serve()
