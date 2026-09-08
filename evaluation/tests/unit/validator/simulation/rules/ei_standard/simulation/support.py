from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

import pandas as pd

from simulation.ei.core.adapters import normalize_gap_wide
from simulation.ei.core.models import (
    ArtifactBundle,
    ArtifactResolution,
    ArtifactSpec,
    CheckConfig,
    CheckResult,
    ComponentConfig,
    QuestionProfile,
    RuleContext,
)
from simulation.ei.rules.ei_standard.simulation import score_simulation


PROMPT_REFS = ("prompt/00714422.txt",)

ContextFactory = Callable[[Iterable[str]], RuleContext]


def _relation() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "solution_id": ["G1"],
            "priority": [1],
            "target_item_code": ["A"],
            "target_qty": [1],
            "sub_item_code": ["B"],
            "sub_qty": [1],
            "new_issue_item_code": [""],
        }
    )


def _scope() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SITE ID": ["S1"],
            "REGION": ["R1"],
            "ITEM CODE": ["A"],
            "NEW": [1],
            "REDEPLOY": [0],
            "DISMANTLE": [0],
        }
    )


def _site_plan() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "site_name": ["S1"],
            "region": ["R1"],
            "site_action": ["install"],
            "week_num": [2],
            "mos_weekly_plan": ["2027WK2"],
            "status": ["scheduled"],
        }
    )


def _final_material() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "site_name": ["S1"],
            "region": ["R1"],
            "action": ["install"],
            "item_code": ["B"],
            "required_qty": [1],
            "original_bom": ["A"],
            "original_bom_qty": [1],
            "install_month": [1],
            "install_wk_label": ["2027WK2"],
            "dismantle_month": [""],
            "dismantle_wk_label": [""],
        }
    )


def _gap_frame() -> pd.DataFrame:
    weeks = [f"WK{week}" for week in range(5, 13)]
    identity = {
        "region": "Region-1",
        "item_code": "ITEM-A",
        "device": "ITEM-A",
        "category": "RRU",
        "total_dismantled": 3,
        "initial_inventory": 1,
        "totalArrive": 3,
        "totalReuse": 2,
        "totalDemand": 5,
        "totalGap": 2,
    }
    weekly_values = {
        "Dismantled": {"WK5": 3},
        "Arrive": {"WK7": 3},
        "DismantledSupply": {"WK7": 3},
        "ReuseConsumed": {"WK7": 2},
        "Demand": {"WK5": 1, "WK7": 4},
        "GAP": {
            "WK5": 0,
            "WK6": 0,
            "WK7": 2,
            "WK8": 2,
            "WK9": 2,
            "WK10": 2,
            "WK11": 2,
            "WK12": 2,
        },
    }
    rows = [
        {
            **{key: "" for key in identity},
            "week": "Date",
            **{week: f"date-{week}" for week in weeks},
        }
    ]
    rows.extend(
        {
            **identity,
            "week": metric,
            **{week: values.get(week, 0) for week in weeks},
        }
        for metric, values in weekly_values.items()
    )
    return pd.DataFrame(rows, columns=[*identity, "week", *weeks])


def _warehouse(*, inbound: float, outbound: float, closing: float) -> dict:
    return {
        ("item-a", 7): {
            "opening": 0,
            "inbound": inbound,
            "outbound": outbound,
            "closing": closing,
        }
    }


def _component(
    rule_ids: Iterable[str],
    parameters: Mapping[str, object],
) -> ComponentConfig:
    return ComponentConfig(
        "simulation",
        "ei.simulation",
        tuple(
            CheckConfig(f"simulation.{rule_id}", PROMPT_REFS)
            for rule_id in rule_ids
        ),
        dict(parameters),
    )


def _resolution(
    role: str,
    *,
    table: pd.DataFrame,
    normalized: object | None = None,
    validation_issues: tuple[dict, ...] = (),
) -> ArtifactResolution:
    return ArtifactResolution(
        role,
        "SELECTED_CANONICAL",
        Path(f"run/{role}.csv"),
        table=table,
        normalized=table if normalized is None else normalized,
        validation_issues=validation_issues,
    )


def _context(
    *,
    rule_ids: Iterable[str],
    parameters: Mapping[str, object],
    sources: frozenset[str],
    resolutions: Mapping[str, ArtifactResolution],
) -> RuleContext:
    selected_rule_ids = tuple(rule_ids)
    component = _component(selected_rule_ids, parameters)
    specs = {
        role: ArtifactSpec(
            role,
            "question" if role in sources else "candidate",
            f"{role}.csv",
            () if role in sources else (f"{role}.csv",),
        )
        for role in resolutions
    }
    profile = QuestionProfile(
        "Q-REFACTOR-CONTRACT",
        "4.13.0",
        ("output",),
        specs,
        {"simulation": component},
        Path("validator.yaml"),
    )
    return RuleContext(
        profile,
        component,
        ArtifactBundle(Path("run"), (), dict(resolutions)),
    )


def material_context(rule_ids: Iterable[str]) -> RuleContext:
    relation = _relation()
    parameters = {
        "s1_substitution_mode": "priority-row-views",
        "s1_traceability_mode": "explicit-origin",
        "s1_check_material_source": False,
        "s1_region_scope": "exact",
        "final_bom_quantity_mode": "signed-action",
        "planning_year": 2027,
        "week_to_month": "calendar",
        "project_start_month": 1,
    }
    return _context(
        rule_ids=rule_ids,
        parameters=parameters,
        sources=frozenset({"substitution_source", "scope_input"}),
        resolutions={
            "material_substitution": _resolution(
                "material_substitution",
                table=relation.copy(),
            ),
            "substitution_source": _resolution(
                "substitution_source",
                table=relation.copy(),
            ),
            "scope_input": _resolution("scope_input", table=_scope()),
            "final_material": _resolution(
                "final_material",
                table=_final_material(),
            ),
            "site_plan": _resolution("site_plan", table=_site_plan()),
        },
    )


def flow_context(rule_ids: Iterable[str]) -> RuleContext:
    gap = _gap_frame()
    normalized_gap, gap_issues = normalize_gap_wide(gap)
    assert not gap_issues, gap_issues
    reuse_warehouse = _warehouse(inbound=3, outbound=0, closing=3)
    new_warehouse = _warehouse(inbound=1, outbound=1, closing=0)
    parameters = {
        "s2_evidence_mode": "gap-wide",
        "s3_evidence_mode": "warehouse",
        "gap_role": "gap",
        "repair_weeks": 2,
        "reuse_rate": 1.0,
        "s3_required_roles": ["reuse_warehouse"],
    }
    return _context(
        rule_ids=rule_ids,
        parameters=parameters,
        sources=frozenset(),
        resolutions={
            "gap": _resolution(
                "gap",
                table=gap,
                normalized=normalized_gap,
                validation_issues=gap_issues,
            ),
            "reuse_warehouse": _resolution(
                "reuse_warehouse",
                table=pd.DataFrame({"week": [7]}),
                normalized=reuse_warehouse,
            ),
            "new_warehouse": _resolution(
                "new_warehouse",
                table=pd.DataFrame({"week": [7]}),
                normalized=new_warehouse,
            ),
        },
    )


def shared_gap_context(rule_ids: Iterable[str]) -> RuleContext:
    gap = _gap_frame()
    normalized_gap, gap_issues = normalize_gap_wide(gap)
    assert not gap_issues, gap_issues
    parameters = {
        "simulation_evidence_mode": "gap-wide",
        "gap_role": "gap",
        "repair_weeks": 2,
        "reuse_rate": 1.0,
    }
    return _context(
        rule_ids=rule_ids,
        parameters=parameters,
        sources=frozenset(),
        resolutions={
            "gap": _resolution(
                "gap",
                table=gap,
                normalized=normalized_gap,
                validation_issues=gap_issues,
            ),
            "reuse_warehouse": _resolution(
                "reuse_warehouse",
                table=pd.DataFrame({"week": [7]}),
                normalized=_warehouse(inbound=3, outbound=0, closing=3),
            ),
        },
    )


def checks_by_rule(context: RuleContext) -> dict[str, CheckResult]:
    return {
        check.check_id.rsplit(".", 1)[-1]: check
        for check in score_simulation(context)
    }


def assert_full_score_contract(check: CheckResult, rule_id: str) -> None:
    assert isinstance(check, CheckResult)
    assert check.check_id == f"simulation.{rule_id}"
    assert check.name
    assert check.score == 100.0
    assert check.status == "PASS"
    assert check.reason_code == ""
    assert check.explanation
    assert check.evidence
    assert check.prompt_refs == PROMPT_REFS
