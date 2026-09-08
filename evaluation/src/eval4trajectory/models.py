from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


class IndicatorStatus(StrEnum):
    PASSED = "passed"
    PARTIAL = "partial"
    FAILED = "failed"
    NOT_OBSERVED = "not_observed"


@dataclass(frozen=True, slots=True)
class TrajectoryMessage:
    index: int
    role: str
    timestamp: str
    text: str

    def excerpt(self, limit: int = 360) -> str:
        compact = " ".join(self.text.split())
        return compact if len(compact) <= limit else compact[: limit - 1] + "…"


@dataclass(frozen=True, slots=True)
class TrajectoryEvidence:
    check_id: str
    failure_tag: str
    signal_labels: tuple[str, ...]
    message_index: int
    trajectory_time: str
    role: str
    excerpt: str
    conclusion: str
    expected: str
    previous_completion_index: int | None = None
    previous_completion_excerpt: str = ""
    repair_index: int | None = None
    repair_excerpt: str = ""
    recurrence: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "failure_tag": self.failure_tag,
            "signal_labels": list(self.signal_labels),
            "message_index": self.message_index,
            "trajectory_time": self.trajectory_time,
            "role": self.role,
            "excerpt": self.excerpt,
            "conclusion": self.conclusion,
            "expected": self.expected,
            "previous_completion_index": self.previous_completion_index,
            "previous_completion_excerpt": self.previous_completion_excerpt,
            "repair_index": self.repair_index,
            "repair_excerpt": self.repair_excerpt,
            "recurrence": self.recurrence,
        }


@dataclass(frozen=True, slots=True)
class GateFailure:
    gate_id: str
    check_id: str
    conclusion: str
    trajectory_time: str

    def as_dict(self) -> dict[str, str]:
        return {
            "gate_id": self.gate_id,
            "check_id": self.check_id,
            "conclusion": self.conclusion,
            "trajectory_time": self.trajectory_time,
        }


@dataclass(frozen=True, slots=True)
class IndicatorResult:
    check_id: str
    title: str
    dimension: str
    max_score: float
    score: float
    status: IndicatorStatus
    summary: str
    failure_tag: str
    n: int
    e: int
    metrics: Mapping[str, Any] = field(default_factory=dict)
    evidence: tuple[TrajectoryEvidence, ...] = ()
    gate_failures: tuple[GateFailure, ...] = ()

    def __post_init__(self) -> None:
        if self.max_score <= 0:
            raise ValueError(f"{self.check_id}: max_score must be positive")
        if not 0 <= self.score <= self.max_score:
            raise ValueError(
                f"{self.check_id}: score {self.score} outside [0, {self.max_score}]"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "title": self.title,
            "dimension": self.dimension,
            "max_score": self.max_score,
            "score": self.score,
            "status": self.status.value,
            "summary": self.summary,
            "failure_tag": self.failure_tag,
            "n": self.n,
            "e": self.e,
            "metrics": dict(self.metrics),
            "evidence": [item.as_dict() for item in self.evidence],
            "gate_failures": [item.as_dict() for item in self.gate_failures],
        }


@dataclass(frozen=True, slots=True)
class TrajectoryReport:
    schema_version: str
    rubric_version: str
    trajectory_file: str
    raw_score: float
    max_score: float
    evaluated_max_score: float
    normalized_score: float | None
    coverage: float
    passed: bool
    dimension_scores: Mapping[str, float]
    dimension_max_scores: Mapping[str, float]
    results: tuple[IndicatorResult, ...]
    gate_failures: tuple[GateFailure, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "rubric_version": self.rubric_version,
            "trajectory_file": self.trajectory_file,
            "raw_score": self.raw_score,
            "max_score": self.max_score,
            "evaluated_max_score": self.evaluated_max_score,
            "normalized_score": self.normalized_score,
            "coverage": self.coverage,
            "passed": self.passed,
            "dimension_scores": dict(self.dimension_scores),
            "dimension_max_scores": dict(self.dimension_max_scores),
            "gate_failures": [item.as_dict() for item in self.gate_failures],
            "results": [item.as_dict() for item in self.results],
            "metadata": dict(self.metadata),
        }

