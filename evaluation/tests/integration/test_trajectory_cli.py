from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path

from eval4trajectory.cli import main


REPO_ROOT = Path(__file__).resolve().parents[3]


def _clear_output(output: Path) -> None:
    for path in output.iterdir():
        if path.name != ".gitignore":
            path.unlink()


class TrajectoryCliTests(unittest.TestCase):
    def test_list_exposes_twelve_indicators(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["list"])
        self.assertEqual(0, code)
        lines = [line for line in output.getvalue().splitlines() if line]
        self.assertEqual(12, len(lines))
        self.assertTrue(lines[0].startswith("D1\t"))
        self.assertTrue(lines[-1].startswith("I3\t"))

    def test_evaluate_writes_trajectory_report_bundle(self):
        fixture_root = REPO_ROOT / "evaluation" / "tests" / "fixtures"
        trajectory = fixture_root / "trajectory" / "cli.html"
        output = fixture_root / "trajectory_cli_output"
        _clear_output(output)
        try:
            code = main(
                [
                    "evaluate",
                    "--trajectory",
                    str(trajectory),
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(0, code)
            self.assertEqual(
                {
                    "business_report.md",
                    "score_result.json",
                    "feedback_trace.csv",
                    "evidence_detail.csv",
                    "gate_failures.json",
                    "regression_cases.json",
                    "improvement_actions.md",
                },
                {path.name for path in output.iterdir() if path.name != ".gitignore"},
            )
            payload = json.loads(
                (output / "score_result.json").read_text(encoding="utf-8")
            )
            self.assertEqual(12, len(payload["results"]))
            self.assertEqual("failed", payload["results"][10]["status"])
        finally:
            _clear_output(output)


if __name__ == "__main__":
    unittest.main()
