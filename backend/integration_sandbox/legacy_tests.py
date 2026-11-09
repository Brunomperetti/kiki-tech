"""Existing service regressions, confined to the same synthetic offline container."""

from .bootstrap import create_sandbox_app

create_sandbox_app()

import pytest  # noqa: E402

raise SystemExit(pytest.main(["tests", "-q", "-p", "no:cacheprovider"]))
