"""Immutable result contracts for EI aggregate metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuleContribution:
    """One leaf's auditable contribution to an aggregate metric."""

    check_id: str
    raw_score: float
    transformed_score: float
    weight: int
    supported: bool
    filled: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "raw_score": self.raw_score,
            "transformed_score": self.transformed_score,
            "weight": self.weight,
            "supported": self.supported,
            "filled": self.filled,
        }


@dataclass(frozen=True)
class AggregateMetric:
    """One of the five EI aggregate outputs for a single question/run."""

    metric_id: str
    group: str
    score: float | None
    status: str
    contributions: tuple[RuleContribution, ...] = ()
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.metric_id,
            "group": self.group,
            "score": self.score,
            "max_score": 100.0,
            "status": self.status,
            "error": self.error,
            "contributions": [value.as_dict() for value in self.contributions],
        }
