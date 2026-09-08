"""Compatibility imports for the EI-owned aggregation package.

New code should import :mod:`simulation.ei.aggregation` directly.
"""

from simulation.ei.aggregation import (  # noqa: F401
    AggregateMetric,
    AggregationConfigurationError,
    AggregationPolicy,
    AggregationRule,
    RuleContribution,
    ScoreBand,
    aggregate_metrics,
    aggregate_total,
    discrete_score,
    load_aggregation_policy,
    piecewise_score,
)

_converted_score = discrete_score

__all__ = [
    "AggregateMetric",
    "AggregationConfigurationError",
    "AggregationPolicy",
    "AggregationRule",
    "RuleContribution",
    "ScoreBand",
    "aggregate_metrics",
    "aggregate_total",
    "discrete_score",
    "load_aggregation_policy",
    "piecewise_score",
]
