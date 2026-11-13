import json
from pathlib import Path
import sys
import unittest
from .reader import query_contract
from .safety import Code, Failure
from .simulated import demo_reader


def main(args):
    try:
        # No argv values, real credentials, URLs or live switches are echoed/accepted.
        if args == ["plan"]:
            result = query_contract()
        elif args == ["demo"]:
            result = demo_reader().read()
        elif args == ["test"]:
            suite = unittest.defaultTestLoader.discover(
                str(Path(__file__).parents[1] / "tests")
            )
            return (
                0
                if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
                else 1
            )
        elif args == ["--help"]:
            result = {
                "commands": ["plan", "demo", "test"],
                "live_mode": "NOT_IMPLEMENTED_OR_AUTHORIZED",
            }
        else:
            raise Failure(Code.COMMAND)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        code = exc.code.value if isinstance(exc, Failure) else Code.INTERNAL.value
        print(
            json.dumps(
                {
                    "error": code,
                    "real_network_enabled": False,
                    "binding_permitted": False,
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
