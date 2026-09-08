from __future__ import annotations

from itertools import permutations

import pytest

from simulation.ei.rules.ei_standard.simulation import score_simulation

from .support import (
    ContextFactory,
    checks_by_rule,
    flow_context,
    material_context,
    shared_gap_context,
)


RULE_FAMILIES: tuple[tuple[ContextFactory, tuple[str, ...]], ...] = (
    (material_context, ("S1", "S5", "S6")),
    (flow_context, ("S2", "S3", "S4")),
    (shared_gap_context, ("S2", "S3")),
)


@pytest.mark.parametrize(("context_factory", "canonical_order"), RULE_FAMILIES)
def test_dispatch_result_does_not_depend_on_rule_order(
    context_factory: ContextFactory,
    canonical_order: tuple[str, ...],
) -> None:
    expected = checks_by_rule(context_factory(canonical_order))

    for rule_order in permutations(canonical_order):
        assert checks_by_rule(context_factory(rule_order)) == expected


def test_dispatch_preserves_profile_check_order() -> None:
    context_factory, canonical_order = RULE_FAMILIES[0]
    for rule_order in permutations(canonical_order):
        result = score_simulation(context_factory(rule_order))

        assert tuple(
            check.check_id.rsplit(".", 1)[-1]
            for check in result
        ) == rule_order


@pytest.mark.parametrize(("context_factory", "rule_ids"), RULE_FAMILIES)
def test_dispatch_returns_the_exact_independent_rule_results(
    context_factory: ContextFactory,
    rule_ids: tuple[str, ...],
) -> None:
    result = score_simulation(context_factory(rule_ids))
    independent = {
        rule_id: score_simulation(context_factory((rule_id,)))[0]
        for rule_id in rule_ids
    }

    assert checks_by_rule(context_factory(rule_ids)) == independent
    assert tuple(result) == tuple(independent[rule_id] for rule_id in rule_ids)
