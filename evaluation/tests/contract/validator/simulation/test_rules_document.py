from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
EI_ROOT = REPOSITORY_ROOT / "evaluation" / "src" / "simulation" / "ei"
RULES_DOCUMENT = EI_ROOT / "rules.md"


class SimulationRulesDocumentContractTests(unittest.TestCase):
    def test_rules_document_matches_the_atomic_ruleset_release(self) -> None:
        ruleset = yaml.safe_load(
            (EI_ROOT / "ruleset.yaml").read_text(encoding="utf-8")
        )
        expected = tuple(ruleset["checks"])
        rules_text = RULES_DOCUMENT.read_text(encoding="utf-8")
        rules_section = rules_text.split("### 2.3 当前规则清单", 1)[1].split(
            "### 2.4 证据与执行边界", 1
        )[0]
        documented = tuple(
            re.findall(
                r"^\| [^|]+ \| `([^`]+\.[^`]+)` \| [^|]+ \|$",
                rules_section,
                flags=re.MULTILINE,
            )
        )

        self.assertEqual(
            ruleset["contract"],
            {
                "id": "simulation.ei",
                "schema_revision": 2,
                "document_type": "ruleset",
            },
        )
        self.assertEqual(ruleset["release"], "4.13.0")
        self.assertEqual(len(expected), 18)
        self.assertEqual(documented, expected)
        self.assertTrue(all(isinstance(check_id, str) for check_id in expected))
        self.assertNotRegex(
            rules_text,
            r"`(?:scheduling|scheduling-pacing|effective-delivery|simulation|reuse-accounting)\.[^`]+` revision \d+",
        )
        for phrase in (
            "ruleset release `4.13.0`",
            "`contracts/ei-contract.schema.json`",
            "规则和聚合不再维护独立 revision",
            "`effective-delivery.O2`",
            "`dismantle-absolute`",
            "calendar_week = planning_year * 100 + week_num",
            "跨年题不得推断",
            "`document_type=component-result`",
            "`document_type=run-score`",
        ):
            self.assertIn(phrase, rules_text)

    def test_ruleset_embeds_aggregation_and_document_freezes_nine_sheets(
        self,
    ) -> None:
        ruleset = yaml.safe_load(
            (EI_ROOT / "ruleset.yaml").read_text(encoding="utf-8")
        )
        config = ruleset["aggregation"]
        rules_text = RULES_DOCUMENT.read_text(encoding="utf-8")

        self.assertFalse((EI_ROOT / "aggregation_config.yaml").exists())
        self.assertEqual(
            sorted(path.name for path in (EI_ROOT / "contracts").glob("*.json")),
            ["ei-contract.schema.json"],
        )
        self.assertEqual(config["policy_id"], "ei-five-metric-aggregate")
        self.assertIn("聚合策略内嵌在 `ruleset.yaml`", rules_text)
        self.assertIn("当前 policy 为 `ei-five-metric-aggregate`", rules_text)
        self.assertIn("不再拥有独立 schema 或 revision", rules_text)

        key_ids = list(config["key"]["rules"])
        all_ids = list(config["all"]["rules"])
        self.assertEqual(
            key_ids,
            [
                "scheduling.C2",
                "scheduling.C6a",
                "scheduling-pacing.O1",
                "simulation.S1",
                "simulation.S5",
            ],
        )
        self.assertEqual(len(all_ids), 17)
        self.assertEqual(
            set(all_ids),
            set(ruleset["checks"]) - {"effective-delivery.O2"},
        )
        for check_id in key_ids + all_ids:
            self.assertIn(f"`{check_id}`", rules_text)

        expected_ladder = [
            {"max_deduction": 5, "score": 90},
            {"max_deduction": 10, "score": 80},
            {"max_deduction": 20, "score": 60},
            {"max_deduction": 40, "score": 40},
            {"max_deduction": 100, "score": 0},
        ]
        for check_id in key_ids:
            self.assertEqual(config["key"]["rules"][check_id]["weight"], 1)
            self.assertEqual(
                config["key"]["rules"][check_id]["ladder"], expected_ladder
            )
        self.assertTrue(
            all(value == {"weight": 1} for value in config["all"]["rules"].values())
        )

        expected_sheets = [
            "O2目标分天梯图",
            "五项分段分天梯图",
            "五项分段分详表",
            "五项离散分天梯图",
            "五项离散分详表",
            "五项原始分天梯图",
            "五项原始分详表",
            "全项原始分天梯图",
            "全项原始分详表",
        ]
        positions = [rules_text.index(f"`{name}`") for name in expected_sheets]
        self.assertEqual(positions, sorted(positions))

    def test_design_contains_only_versioned_capability_checklists(self) -> None:
        design_root = REPOSITORY_ROOT / "design"
        files = sorted(
            path.relative_to(design_root).as_posix()
            for path in design_root.rglob("*")
            if path.is_file()
        )
        self.assertEqual(
            files,
            [
                "运筹智能体考点清单v2.3.xlsx",
                "运筹智能体考点清单v2.4.xlsx",
                "运筹智能体考点清单v2.5.xlsx",
                "运筹智能体考点清单v2.6.xlsx",
            ],
        )

    def test_package_has_one_rules_document_and_no_nested_readme(self) -> None:
        self.assertTrue(RULES_DOCUMENT.is_file())
        self.assertFalse((EI_ROOT / "README.md").exists())
        self.assertFalse((EI_ROOT / "rules" / "ei_standard" / "README.md").exists())


if __name__ == "__main__":
    unittest.main()
