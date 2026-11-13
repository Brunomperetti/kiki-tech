"""Host startup smoke test with NO query authorization, credentials or network.

The genuine-query command is never invoked: the child receives no arguments.
"""

import json
from pathlib import Path
import subprocess
import sys
import unittest


class Entrypoint(unittest.TestCase):
    def test_independent_no_site_process_refuses_missing_authorization(self):
        program = Path(__file__).resolve().with_name("query.py")
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-B", str(program)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertEqual(output["error"], "UNSUPPORTED_OFFLINE_COMMAND")
        self.assertFalse(output["query_completed"])
        self.assertEqual(output["request_attempts"], 0)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
