from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from simulation.ei.aggregation import AggregationPolicy
from simulation.ei.core.adapters import resolve_artifacts
from simulation.ei.core.engine import score_components, score_run
from simulation.ei.core.models import (
    ArtifactBundle,
    ArtifactSpec,
    CheckConfig,
    ComponentConfig,
    QuestionProfile,
)
from simulation.ei.rules.ei_standard._shared import leaf

from evaluation.tests.helpers.simulation_artifact_factory import layout, write_csv


class SelectiveScoringTests(unittest.TestCase):
    def test_adapter_loads_only_requested_roles(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            base = Path(value)
            repo, question_dir, run = layout(base)
            write_csv(question_dir / "data/used.csv", [{"A": 1}])
            write_csv(question_dir / "data/skipped.csv", [{"B": 2}])
            profile = QuestionProfile(
                question_id="Q",
                ruleset_release="4.13.0",
                artifact_roots=(".",),
                artifacts={
                    "used": ArtifactSpec(
                        "used", "question", "data/used.csv", schema="generic"
                    ),
                    "skipped": ArtifactSpec(
                        "skipped", "question", "data/skipped.csv", schema="generic"
                    ),
                },
                components={},
                path=question_dir / "validator.yaml",
            )

            bundle = resolve_artifacts(profile, run, repo, roles=("used",))

            self.assertEqual(set(bundle.artifacts), {"used"})
            self.assertTrue(bundle.get("used").usable)

    def test_engine_executes_only_requested_check(self) -> None:
        component = ComponentConfig(
            name="scheduling",
            scorer="test.selective",
            checks=(
                CheckConfig("scheduling.C6a", ("prompt:C6a",)),
                CheckConfig("scheduling.C6b", ("prompt:C6b",)),
            ),
        )
        profile = QuestionProfile(
            question_id="Q",
            ruleset_release="4.13.0",
            artifact_roots=(".",),
            artifacts={},
            components={"scheduling": component},
            path=Path("validator.yaml"),
        )
        bundle = ArtifactBundle(Path("run"), (), {})

        def scorer(context):
            checks = [
                leaf(context, local_id, local_id, 1.0, "ok")
                for local_id in (
                    check.check_id.split(".", 1)[1]
                    for check in context.component.checks
                )
            ]
            return tuple(checks)

        with (
            patch.dict(
                "simulation.ei.core.engine.SCORERS",
                {"test.selective": scorer},
            ),
        ):
            results = score_components(
                profile,
                bundle,
                checks=("scheduling.C6a",),
                root=Path("."),
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(
            [check.check_id for check in results[0].checks],
            ["scheduling.C6a"],
        )
        self.assertEqual(results[0].status, "SCORED")


if __name__ == "__main__":
    unittest.main()


@pytest.mark.parametrize(
    ("change", "message"),
    (
        ("profile_release", "profile ruleset release"),
        ("requested_release", "requested ruleset release"),
        ("policy_release", "policy ruleset release"),
        ("coherent_old_release", "profile ruleset release"),
    ),
)
def test_score_run_rejects_caller_supplied_stale_scoring_identity(
    tmp_path: Path,
    change: str,
    message: str,
) -> None:
    profile = QuestionProfile(
        question_id="Q",
        ruleset_release="4.13.0",
        artifact_roots=(".",),
        artifacts={},
        components={},
        path=tmp_path / "validator.yaml",
    )
    policy: AggregationPolicy | None = None
    requested_release: str | None = None
    if change == "profile_release":
        profile = replace(profile, ruleset_release="4.10.0")
    elif change == "requested_release":
        requested_release = "4.10.0"
    elif change == "policy_release":
        policy = AggregationPolicy("4.10.0", "test", ())
    else:
        profile = replace(profile, ruleset_release="4.10.0")
        policy = AggregationPolicy("4.10.0", "test", ())
        requested_release = "4.10.0"

    with (
        patch(
            "simulation.ei.core.engine.load_ruleset",
            return_value={
                "release": "4.13.0",
            },
        ),
        patch("simulation.ei.core.engine.resolve_artifacts") as resolver,
        pytest.raises(ValueError, match=message),
    ):
        score_run(
            "Q",
            tmp_path / "run",
            root=tmp_path,
            repo=tmp_path,
            components=(),
            aggregation_policy=policy,
            question_profile=profile,
            release=requested_release,
        )
    resolver.assert_not_called()
