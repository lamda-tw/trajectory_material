"""Candidate-owned EI evidence compiled once and shared across rule families."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from simulation.ei.core.models import ArtifactBundle, QuestionProfile

from .scheduling.parsing import _candidate_plan
from .simulation.time import _scheduled_plan_from_candidate


@dataclass(frozen=True)
class PreparedRunRuleData:
    """Reusable candidate plan views keyed by their parsing contract."""

    candidate_plans: Mapping[str, pd.DataFrame]
    scheduled_plans: Mapping[str, pd.DataFrame]


def _week_source(scorer: str, parameters: Mapping[str, object]) -> str:
    # O1 historically parses with the default reconcile contract.  Keeping
    # that behavior here avoids turning a performance change into rule drift.
    if scorer == "ei.pacing":
        return "reconcile"
    return str(parameters.get("project_week_source", "reconcile"))


def prepare_run_rule_data(
    profile: QuestionProfile,
    artifacts: ArtifactBundle,
) -> PreparedRunRuleData:
    """Compile each requested site-plan interpretation at most once per run."""

    resolved = artifacts.get("site_plan")
    raw_plan = resolved.table if resolved is not None and resolved.usable else None
    if not isinstance(raw_plan, pd.DataFrame):
        return PreparedRunRuleData({}, {})

    modes = {
        _week_source(component.scorer, component.parameters)
        for component in profile.components.values()
        if component.scorer in {"ei.scheduling", "ei.pacing", "ei.simulation"}
    }
    candidate_plans: dict[str, pd.DataFrame] = {}
    scheduled_plans: dict[str, pd.DataFrame] = {}
    for mode in sorted(modes):
        try:
            plan = _candidate_plan(raw_plan, project_week_source=mode)
        except Exception:  # noqa: BLE001 - individual scorers retain diagnostics
            continue
        candidate_plans[mode] = plan
        scheduled_plans[mode] = _scheduled_plan_from_candidate(raw_plan, plan)
    return PreparedRunRuleData(candidate_plans, scheduled_plans)


__all__ = ["PreparedRunRuleData", "prepare_run_rule_data"]
