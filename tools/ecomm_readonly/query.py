"""Future authorized Linux/WSL entrypoint. Do not run without separate approval.

Run with python3 -I -S -B; never loads site hooks, environment files or KIKI.
"""

from pathlib import Path
import json
import resource
import signal
import sys


def execute():
    if not sys.flags.isolated or not sys.flags.no_site or not sys.dont_write_bytecode:
        print(
            json.dumps({"error": "ISOLATED_PYTHON_REQUIRED", "query_completed": False})
        )
        return 2
    resource.setrlimit(resource.RLIMIT_AS, (160 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (5, 6))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    # Only the reader directory is added. Isolated mode excludes cwd/PYTHONPATH.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ecomm_reader.query import main
    from ecomm_reader.safety import Code, Failure

    def expired(signum, frame):
        raise Failure(Code.TIME)

    signal.signal(signal.SIGALRM, expired)
    signal.alarm(30)
    try:
        return main(sys.argv[1:])
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    try:
        result = execute()
    except (Exception, KeyboardInterrupt):
        # Bootstrap exceptions also must not echo paths, environment or secrets.
        print(
            json.dumps({"error": "INDEPENDENT_QUERY_FAILED", "query_completed": False})
        )
        result = 2
    raise SystemExit(result)
