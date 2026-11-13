"""Isolated Python entrypoint; only this directory plus the standard library."""

from pathlib import Path
import resource
import sys

sys.dont_write_bytecode = True
resource.setrlimit(resource.RLIMIT_AS, (160 * 1024 * 1024, 160 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_CPU, (5, 6))
resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ecomm_reader.cli import main  # noqa: E402

raise SystemExit(main(sys.argv[1:]))
