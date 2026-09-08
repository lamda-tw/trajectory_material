from __future__ import annotations

import unittest

from eval4trajectory.evaluator import TrajectoryEvaluator
from eval4trajectory.models import IndicatorStatus, TrajectoryMessage


def message(index: int, role: str, text: str) -> TrajectoryMessage:
    return TrajectoryMessage(index, role, f"2026/01/01 10:{index:02d}:00", text)


class TrajectoryEvaluatorTests(unittest.TestCase):
    def test_failure_precedes_later_pass_evidence(self):
        report = TrajectoryEvaluator().evaluate_messages(
            [
                message(1, "用户", "The DU below is missing: S1"),
                message(2, "AI", "Found the root cause. The DU was lost in the pipeline."),
                message(3, "AI", "All active DUs unique; coverage 100%."),
            ]
        )
        result = next(item for item in report.results if item.check_id == "S4")
        self.assertEqual(IndicatorStatus.FAILED, result.status)
        self.assertEqual(0, result.score)
        self.assertEqual(1, result.e)

    def test_explicit_pass_without_failure_scores_full(self):
        report = TrajectoryEvaluator().evaluate_messages(
            [
                message(
                    1,
                    "AI",
                    "QTY (Use This) is the preferred source and fallback uses Quantity (Dont Use).",
                )
            ]
        )
        result = next(item for item in report.results if item.check_id == "D2")
        self.assertEqual(IndicatorStatus.PASSED, result.status)
        self.assertEqual(5, result.score)
        self.assertEqual(1, result.n)
        self.assertEqual(0, result.e)

    def test_unobserved_is_not_automatically_passed(self):
        report = TrajectoryEvaluator().evaluate_messages(
            [message(1, "用户", "Please build a dashboard.")]
        )
        result = next(item for item in report.results if item.check_id == "P3")
        self.assertEqual(IndicatorStatus.NOT_OBSERVED, result.status)
        self.assertEqual(0, result.score)
        self.assertIsNone(report.normalized_score)
        self.assertEqual(0, report.coverage)

    def test_recurrence_caps_recovery_score(self):
        report = TrajectoryEvaluator().evaluate_messages(
            [
                message(1, "用户", "Do not see any dashboard."),
                message(
                    2,
                    "AI",
                    "Root cause found. Expected direct URL fixed. All checks pass. Deployed.",
                ),
                message(3, "用户", "The dashboard link is empty."),
                message(
                    4,
                    "AI",
                    "Root cause found. Expected direct URL fixed. All checks pass. Deployed.",
                ),
            ]
        )
        recovery = next(item for item in report.results if item.check_id == "I3")
        self.assertLessEqual(recovery.score, 2)
        self.assertEqual(1, recovery.metrics["recurrences"])
        self.assertTrue(any(item.recurrence for item in recovery.evidence))


if __name__ == "__main__":
    unittest.main()
