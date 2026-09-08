"""C6b delivery-batch order."""

from collections import defaultdict

from simulation.ei.core.models import CheckResult, RuleContext

from .._shared import leaf
from ..common import _key
from .evidence import SchedulingEvidence
from .parsing import batch_for, batch_order_value


def score_c6b(context: RuleContext, evidence: SchedulingEvidence) -> CheckResult:
    contract = evidence.parameters["c6b_contract"]
    order_mode = str(contract["order_mode"])
    order_scope = str(contract["scope"])
    batch_kind = str(evidence.parameters["batch_kind"])
    if contract.get("event") != "first_install_week":
        raise ValueError("invalid C6b event")
    if order_mode not in {"numeric_ascending", "source_sequence"}:
        raise ValueError("invalid C6b order mode")
    if order_scope not in {"region", "global"}:
        raise ValueError("invalid C6b scope")

    batches_by_scope: dict[str, list[str]] = defaultdict(list)
    for row in evidence.batch_rows:
        scope_key = _key(row["region"]) if order_scope == "region" else "all"
        batch = str(row["batch"])
        if batch not in batches_by_scope[scope_key]:
            batches_by_scope[scope_key].append(batch)
    ordered_by_scope: dict[str, list[str]] = {}
    for scope_key, batches in batches_by_scope.items():
        if order_mode == "numeric_ascending":
            values = {batch: batch_order_value(batch) for batch in batches}
            if any(value is None for value in values.values()):
                raise ValueError(f"C6b numeric order contains a non-numeric {batch_kind} ID")
            ordered_by_scope[scope_key] = sorted(
                batches,
                key=lambda batch: (float(values[batch]), batch.casefold()),
            )
        else:
            ordered_by_scope[scope_key] = list(batches)

    event_week: dict[tuple[str, str], int] = {}
    install_rows = evidence.plan[
        (evidence.plan["action"] == "install")
        & (evidence.plan["status"] != "unscheduled")
    ]
    candidate_install = install_rows[install_rows["project_week"].notna()]
    week_issue_counts = {
        str(issue): int(count)
        for issue, count in install_rows.loc[
            install_rows["week_issue"] != "", "week_issue"
        ].value_counts().items()
    }
    unmapped_install_row_count = 0
    for _, row in candidate_install.iterrows():
        batch = batch_for(str(row["site_key"]), evidence.batch_map)
        if batch is None:
            unmapped_install_row_count += 1
            continue
        scope_key = _key(row["region"]) if order_scope == "region" else "all"
        key = (scope_key, batch)
        week = int(row["project_week"])
        event_week[key] = min(event_week.get(key, week), week)

    pair_details: list[dict[str, object]] = []
    passed = 0
    candidate_pair_count = 0
    candidate_batch_count = 0
    authoritative_pair_count = sum(
        max(len(sequence) - 1, 0) for sequence in ordered_by_scope.values()
    )
    for scope_key, sequence in sorted(ordered_by_scope.items()):
        candidate_sequence = [
            batch for batch in sequence if (scope_key, batch) in event_week
        ]
        candidate_batch_count += len(candidate_sequence)
        for predecessor, successor in zip(candidate_sequence, candidate_sequence[1:]):
            left_week = event_week[(scope_key, predecessor)]
            right_week = event_week[(scope_key, successor)]
            status = "PASS" if left_week <= right_week else "ORDER_VIOLATION"
            candidate_pair_count += 1
            passed += int(status == "PASS")
            pair_details.append(
                {
                    "scope": scope_key,
                    "predecessor": predecessor,
                    "successor": successor,
                    "predecessor_week": left_week,
                    "successor_week": right_week,
                    "status": status,
                }
            )
    order_accuracy = passed / candidate_pair_count if candidate_pair_count else 0.0
    pair_coverage = (
        candidate_pair_count / authoritative_pair_count
        if authoritative_pair_count
        else 0.0
    )
    rate = passed / authoritative_pair_count if authoritative_pair_count else 0.0
    if candidate_pair_count:
        reason_code = ""
    elif candidate_install.empty and week_issue_counts.get("WEEK_CONFLICT", 0):
        reason_code = "WEEK_CONFLICT"
    elif candidate_install.empty and not install_rows.empty:
        reason_code = "UNPARSEABLE_WEEK"
    elif not candidate_install.empty and not event_week:
        reason_code = "UNMAPPED_BATCH"
    else:
        reason_code = "INSUFFICIENT_ORDER_EVIDENCE"
    return leaf(
        context,
        "C6b",
        "Delivery batch order",
        rate,
        "Candidate batch order accuracy is coverage-adjusted against the full authoritative adjacent-pair universe",
        {
            "batch_kind": batch_kind,
            "order_mode": order_mode,
            "scope": order_scope,
            "event": "first_install_week",
            "authoritative_batch_count": sum(len(value) for value in ordered_by_scope.values()),
            "candidate_batch_count": candidate_batch_count,
            "authoritative_pair_count": authoritative_pair_count,
            "candidate_pair_count": candidate_pair_count,
            "pair_count": candidate_pair_count,
            "order_accuracy": order_accuracy,
            "pair_coverage": pair_coverage,
            "passed_pairs": passed,
            "order_violation_pairs": candidate_pair_count - passed,
            "candidate_install_row_count": len(install_rows),
            "valid_install_week_row_count": len(candidate_install),
            "unmapped_install_row_count": unmapped_install_row_count,
            "week_issue_counts": week_issue_counts,
            "pairs": pair_details,
        },
        reason_code=reason_code,
    )
