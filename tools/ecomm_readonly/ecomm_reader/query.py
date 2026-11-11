"""Explicit future one-shot command. Never executed by offline plan/demo/test."""

import json

from .authorization import load_authorization
from .native import prepare, require_direct_environment
from .reader import InventoryReader
from .safety import Code, Failure


def arguments(args):
    allowed = {"--credential-file", "--scope-evidence", "--max-pages"}
    if not args or args[0] != "--authorize-one-query" or len(args) not in (5, 7):
        raise Failure(Code.COMMAND)
    options = {}
    for i in range(1, len(args), 2):
        if args[i] not in allowed or args[i] in options:
            raise Failure(Code.COMMAND)
        options[args[i]] = args[i + 1]
    if not {"--credential-file", "--scope-evidence"}.issubset(options):
        raise Failure(Code.COMMAND)
    if options.get("--max-pages", "1") not in ("1", "2"):
        raise Failure(Code.COMMAND)
    if options["--credential-file"] == options["--scope-evidence"]:
        raise Failure(Code.COMMAND)
    return options


def main(args):
    reader = None
    try:
        options = arguments(args)
        # Refuse this managed/proxied deployment BEFORE opening any secret file.
        require_direct_environment()
        grant = load_authorization(
            options["--credential-file"],
            options["--scope-evidence"],
            max_pages=int(options.get("--max-pages", "1")),
        )
        resolver, wire = prepare(grant)
        reader = InventoryReader.authorized_query(grant, resolver, wire)
        print(json.dumps(reader.read(), ensure_ascii=False, indent=2))
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        print(
            json.dumps(
                {
                    "error": exc.code.value
                    if isinstance(exc, Failure)
                    else Code.INTERNAL.value,
                    "query_completed": False,
                    "request_attempts": reader._requests if reader is not None else 0,
                    "binding_permitted": False,
                    "provider_side_effects": "NOT_VERIFIED_IF_A_REQUEST_WAS_SENT",
                }
            )
        )
        return 2
