from __future__ import annotations

import unittest
from pathlib import Path

from eval4trajectory.parser import parse_trajectory


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "trajectory"


class TrajectoryParserTests(unittest.TestCase):
    def test_reads_only_visible_message_text(self):
        messages = parse_trajectory(FIXTURES / "visible.html")
        self.assertEqual(2, len(messages))
        self.assertEqual("用户", messages[0].role)
        self.assertEqual("Hello agent.", messages[0].text)
        self.assertIn("Visible answer.", messages[1].text)
        self.assertIn("Verified", messages[1].text)
        self.assertNotIn("private reasoning", messages[1].text)
        self.assertNotIn("secret tool output", messages[1].text)

    def test_rejects_non_export_html(self):
        with self.assertRaisesRegex(ValueError, "no exported messages"):
            parse_trajectory(FIXTURES / "empty.html")

    def test_preserves_interrupted_message_without_visible_text(self):
        messages = parse_trajectory(FIXTURES / "interrupted.html")
        self.assertEqual(1, len(messages))
        self.assertEqual("", messages[0].text)


if __name__ == "__main__":
    unittest.main()
