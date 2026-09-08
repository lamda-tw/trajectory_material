"""C5 Prompt-scoped installation quantity."""

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd

from simulation.ei.core.models import CheckResult, RuleContext

from .._shared import leaf
from ..drop_selection import compile_seeded_drop_selection
from .evidence import SchedulingEvidence
from .parsing import batch_for


def score_c5(context: RuleContext, evidence: SchedulingEvidence) -> CheckResult:
    skip_rate = float(evidence.parameters.get("skip_rate", 0.0))
    skip_pool_scope = str(evidence.parameters["skip_pool_scope"])
    if skip_pool_scope not in {"batch", "region-batch", "region"}:
        raise ValueError("invalid C5 skip pool scope")

    def pool_for(site: str) -> tuple[str, str] | None:
        batch = batch_for(site, evidence.batch_map)
        if batch is None:
            return None
        region = str(site).partition("|")[0]
        return (
            "",
            str(batch),
        ) if skip_pool_scope == "batch" else (
            region,
            str(batch) if skip_pool_scope == "region-batch" else "",
        )

    expected_install_sites = set(
        evidence.expected.loc[
            evidence.expected["action"] == "install",
            "site_key",
        ].map(str)
    )
    valid_actual_installs = evidence.plan[
        (evidence.plan["action"] == "install")
        & (evidence.plan["week_issue"] == "")
        & evidence.plan["project_week"].notna()
    ]
    actual_install_sites = set(valid_actual_installs["site_key"].map(str))

    selection_contract = evidence.parameters.get("drop_selection_contract")
    if selection_contract is not None:
        if not isinstance(selection_contract, dict):
            raise ValueError("C5 drop_selection_contract must be a mapping")
        selection = evidence.drop_selection or compile_seeded_drop_selection(
            evidence.expected,
            evidence.batch_map,
            batch_kind=str(evidence.parameters["batch_kind"]),
            drop_rate=skip_rate,
            pool_scope=skip_pool_scope,
            contract=selection_contract,
        )
        expected_retained = set(selection.retained_install_site_keys)
        actual_authority = actual_install_sites & set(
            selection.full_install_site_keys
        )
        missing_retained = expected_retained - actual_authority
        forbidden_dropped = actual_authority & set(
            selection.dropped_install_site_keys
        )
        identity_deviation = len(missing_retained) + len(forbidden_dropped)
        denominator = len(expected_retained)
        pool_targets = []
        for pool in selection.pools:
            pool_sites = set(pool["install_site_keys"])
            actual_in_pool = actual_authority & pool_sites
            expected_in_pool = (
                set(selection.retained_install_site_keys) & pool_sites
            )
            pool_targets.append(
                {
                    **pool,
                    "actual_sites": len(actual_in_pool),
                    "missing_retained_sites": len(expected_in_pool - actual_in_pool),
                    "forbidden_dropped_sites": len(
                        actual_in_pool & set(selection.dropped_install_site_keys)
                    ),
                }
            )
        return leaf(
            context,
            "C5",
            "Delivery batch quantity and deterministic Drop identity",
            1.0 - identity_deviation / denominator if denominator else 0.0,
            "Scheduled installation identities must equal the Prompt-authorized "
            "fixed-seed Drop result",
            {
                "batch_kind": evidence.parameters["batch_kind"],
                "skip_pool_scope": skip_pool_scope,
                "skip_rate": skip_rate,
                "install_pool_sites": len(selection.full_install_site_keys),
                "expected": denominator,
                "actual": len(actual_authority),
                "absolute_deviation": identity_deviation,
                "identity_comparison": "missing_retained + forbidden_dropped",
                "missing_retained_site_count": len(missing_retained),
                "missing_retained_site_keys": sorted(missing_retained),
                "forbidden_dropped_site_count": len(forbidden_dropped),
                "forbidden_dropped_site_keys": sorted(forbidden_dropped),
                "drop_selection": selection.evidence(),
                "pool_targets": pool_targets,
            },
            reason_code=(
                "DROP_IDENTITY_MISMATCH" if identity_deviation else ""
            ),
        )

    expected_counts: dict[tuple[str, str], int] = defaultdict(int)
    actual_counts: dict[tuple[str, str], int] = defaultdict(int)
    for site in expected_install_sites:
        pool = pool_for(site)
        if pool is not None:
            expected_counts[pool] += 1
    for site in actual_install_sites:
        pool = pool_for(site)
        if pool is not None:
            actual_counts[pool] += 1
    target_counts = {
        pool: int(
            (
                Decimal(count) * (Decimal("1") - Decimal(str(skip_rate)))
            ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        for pool, count in expected_counts.items()
    }
    denominator = sum(target_counts.values())
    deviation = sum(
        abs(actual_counts.get(pool, 0) - target)
        for pool, target in target_counts.items()
    )
    pool_targets = [
        {
            "region": region,
            "batch": batch or None,
            "install_pool_sites": expected_counts[(region, batch)],
            "target_sites": target_counts[(region, batch)],
            "actual_sites": actual_counts.get((region, batch), 0),
        }
        for region, batch in sorted(target_counts)
    ]
    return leaf(
        context,
        "C5",
        "Delivery batch quantity",
        1.0 - deviation / denominator if denominator else 0.0,
        "Scheduled installation counts are compared with Prompt-authorized Drop-pool targets",
        {
            "batch_kind": evidence.parameters["batch_kind"],
            "skip_pool_scope": skip_pool_scope,
            "skip_rate": skip_rate,
            "install_pool_sites": sum(expected_counts.values()),
            "expected": denominator,
            "actual": sum(actual_counts.values()),
            "absolute_deviation": deviation,
            "pool_targets": pool_targets,
        },
    )
