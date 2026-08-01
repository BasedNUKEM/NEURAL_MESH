"""CLI tests for v0.20 operational commands."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest


class TestOperationalCLI(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [os.environ.get("PYTHON", "python3"), "-m", "neural_mesh", *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_consolidate_and_sleep_commands(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "mesh.db")
            consolidate = self.run_cli("consolidate", "--db", db)
            sleep = self.run_cli("sleep", "--db", db)
            self.assertEqual(consolidate.returncode, 0, consolidate.stderr)
            self.assertEqual(sleep.returncode, 0, sleep.stderr)
            self.assertIn("promoted", json.loads(consolidate.stdout))
            self.assertIn("pruned", json.loads(sleep.stdout))

    def test_pointer_put_and_summary_commands(self):
        with tempfile.TemporaryDirectory() as d:
            source = os.path.join(d, "trace.txt")
            with open(source, "w") as f:
                f.write("TRACE" * 100)
            put = self.run_cli("pointer-put", source, "--root", d, "--label", "trace")
            self.assertEqual(put.returncode, 0, put.stderr)
            pointer = json.loads(put.stdout)["pointer"]
            summary = self.run_cli("pointer-summary", pointer, "--root", d,
                                   "--max-chars", "40")
            self.assertEqual(summary.returncode, 0, summary.stderr)
            self.assertLess(len(json.loads(summary.stdout)["summary"]), 500)

    def test_pointer_summary_rejects_wrong_scheme_for_existing_object(self):
        with tempfile.TemporaryDirectory() as d:
            source = os.path.join(d, "trace.txt")
            with open(source, "w") as f:
                f.write("private trace")
            put = self.run_cli("pointer-put", source, "--root", d, "--label", "trace")
            pointer = json.loads(put.stdout)["pointer"]
            forged = "mesh://../../trace/" + pointer.rsplit("/", 1)[-1]
            summary = self.run_cli("pointer-summary", forged, "--root", d)
            self.assertNotEqual(summary.returncode, 0)
            self.assertNotIn("private trace", summary.stdout)


if __name__ == "__main__":
    unittest.main()
