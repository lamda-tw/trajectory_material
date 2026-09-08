"""EI-owned aggregation policies and services."""

from .config import (
    AggregationConfigurationError,
    AggregationPolicy,
    AggregationRule,
    ScoreBand,
    load_aggregation_policy,
)
from .methods import discrete_score, piecewise_score
from .models import AggregateMetric, RuleContribution
from .service import aggregate_metrics, aggregate_total

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
