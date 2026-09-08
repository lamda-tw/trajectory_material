"""C6a install/dismantle lag at Prompt-configured batch or site scope."""

from collections import defaultdict

import pandas as pd

from simulation.ei.core.models import CheckResult, RuleContext

from .._shared import leaf, not_applicable_leaf
from .evidence import SchedulingEvidence
from .parsing import batch_for


def score_c6a(context: RuleContext, evidence: SchedulingEvidence) -> CheckResult:
    contract = evidence.parameters["c6a_contract"]
    batch_kind = str(evidence.parameters["batch_kind"])
    scope = str(contract.get("scope", "batch"))
    direction = str(contract.get("direction", "install_then_dismantle"))
    relation = str(contract["relation"])
    offset = int(contract["lag_weeks"])
    if (
        batch_kind not in {"cluster", "mocn"}
        or scope not in {"batch", "site"}
        or direction != "install_then_dismantle"
        or relation not in {"minimum", "exact"}
    ):
        raise ValueError("invalid C6a interval contract")

    candidate_units: dict[str, dict[str, list[pd.Series]]] = defaultdict(
        lambda: {"install": [], "dismantle": []}
    )
    unmapped_candidate_actions = 0
    actions = evidence.plan[
        evidence.plan["action"].isin({"install", "dismantle"})
        & (evidence.plan["status"] != "unscheduled")
    ]
    for _, row in actions.iterrows():
        site_key = str(row["site_key"])
        batch_key = batch_for(site_key, evidence.batch_map)
        if batch_key is None:
            unmapped_candidate_actions += 1
            continue
        unit_key = site_key if scope == "site" else str(batch_key)
        candidate_units[unit_key][str(row["action"])].append(row)

    comparable = {
        key: action_rows
        for key, action_rows in candidate_units.items()
        if action_rows["install"] and action_rows["dismantle"]
    }
    valid = 0
    invalid_week_units = 0
    diagnostics: list[dict[str, object]] = []
    for unit_key, action_rows in sorted(comparable.items()):
        rows = action_rows["install"] + action_rows["dismantle"]
        invalid_rows = [
            row
            for row in rows
            if bool(row["week_issue"]) or pd.isna(row["project_week"])
        ]
        unit_identity = {
            "unit": unit_key,
            "site_key" if scope == "site" else "batch": unit_key,
        }
        if invalid_rows:
            invalid_week_units += 1
            diagnostics.append(
                {
                    **unit_identity,
                    "reason": "INVALID_WEEK",
                    "invalid_time_row_count": len(invalid_rows),
                    "invalid_time_rows": [
                        {
                            "source_row": int(row["source_row"]),
                            "action": str(row["action"]),
                            "week_issue": str(
                                row["week_issue"] or "UNPARSEABLE_WEEK"
                            ),
                        }
                        for row in invalid_rows[:20]
                    ],
                }
            )
            continue
        install_finish = max(
            int(row["project_week"]) for row in action_rows["install"]
        )
        dismantle_start = min(
            int(row["project_week"]) for row in action_rows["dismantle"]
        )
        actual_offset = dismantle_start - install_finish
        passed = (
            actual_offset >= offset
            if relation == "minimum"
            else actual_offset == offset
        )
        valid += int(passed)
        if not passed:
            diagnostics.append(
                {
                    **unit_identity,
                    "reason": "INTERVAL_VIOLATION",
                    "install_finish": install_finish,
                    "dismantle_start": dismantle_start,
                    "actual_offset": actual_offset,
                    "expected_relation": relation,
                    "expected_offset": offset,
                }
            )

    details: dict[str, object] = {
        "batch_kind": batch_kind,
        "scope": scope,
        "direction": direction,
        "relation": relation,
        "lag_weeks": offset,
        "candidate_units": len(candidate_units),
        "comparable_units": len(comparable),
        "not_comparable_units": len(candidate_units) - len(comparable),
        "unmapped_candidate_actions": unmapped_candidate_actions,
        "valid": valid,
        "invalid": len(comparable) - valid,
        "invalid_week_units": invalid_week_units,
        "interval_violation_units": len(comparable) - valid - invalid_week_units,
        "failures": diagnostics,
    }
    # Preserve the established batch-scope evidence names for existing report
    # consumers while exposing neutral unit names for both contracts.
    if scope == "batch":
        details.update(
            {
                "candidate_batches": len(candidate_units),
                "comparable_batches": len(comparable),
                "not_comparable_batches": len(candidate_units) - len(comparable),
                "invalid_week_batches": invalid_week_units,
                "interval_violation_batches": (
                    len(comparable) - valid - invalid_week_units
                ),
            }
        )
    else:
        details.update(
            {
                "candidate_sites": len(candidate_units),
                "comparable_sites": len(comparable),
                "not_comparable_sites": len(candidate_units) - len(comparable),
                "invalid_week_sites": invalid_week_units,
                "interval_violation_sites": (
                    len(comparable) - valid - invalid_week_units
                ),
            }
        )

    if not comparable:
        return not_applicable_leaf(
            context,
            "C6a",
            "Install/dismantle lag",
            f"No candidate {scope} contains both install and dismantle actions",
            details,
        )
    return leaf(
        context,
        "C6a",
        "Install/dismantle lag",
        valid / len(comparable),
        "For candidate units with both phases, compare phase boundaries using "
        "the Prompt-configured scope, direction, and interval relation",
        details,
    )
