"""Typed, in-memory contracts for Simulation validator v4.13."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ArtifactSpec:
    """One prompt-authorized candidate or question-input artifact role."""

    role: str
    source: str
    path: str
    filenames: tuple[str, ...] = ()
    schema: str = "generic"
    required: bool = True
    schema_options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CheckConfig:
    """One applicable atomic check in a component."""

    check_id: str
    prompt_refs: tuple[str, ...]


@dataclass(frozen=True)
class ComponentConfig:
    """Execution configuration for one business component."""

    name: str
    scorer: str
    checks: tuple[CheckConfig, ...]
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QuestionProfile:
    """Validated question profile bound to one immutable ruleset release."""

    question_id: str
    ruleset_release: str
    artifact_roots: tuple[str, ...]
    artifacts: dict[str, ArtifactSpec]
    components: dict[str, ComponentConfig]
    path: Path
    release_status: str = "active"
    blocking_reasons: tuple[str, ...] = ()
    question_dir: Path | None = None
    question_kind: str = "evaluation"
    legacy_shared_data: bool = False

    @property
    def enabled_components(self) -> tuple[str, ...]:
        return tuple(self.components)


@dataclass(frozen=True)
class ArtifactCandidate:
    """One candidate considered for an artifact role."""

    path: Path
    required_coverage: float
    prompt_filename: bool
    common_parent_suffix: int
    usable: bool
    error: str = ""
    canonical: bool = False


@dataclass
class ArtifactResolution:
    """Resolved raw evidence for one artifact role."""

    role: str
    status: str
    selected_path: Path | None
    candidates: tuple[ArtifactCandidate, ...] = ()
    table: Any | None = None
    normalized: Any | None = None
    error: str = ""
    validation_issues: tuple[dict[str, Any], ...] = ()
    quantity_error_count: int = 0
    quantity_errors: tuple[dict[str, Any], ...] = ()
    resolution_diagnostics: tuple[dict[str, Any], ...] = ()

    @property
    def usable(self) -> bool:
        return (
            self.status in {"SELECTED_CANONICAL", "SELECTED_FALLBACK"}
            and self.selected_path is not None
            and not self.error
            and self.normalized is not None
        )


@dataclass
class ArtifactBundle:
    """All candidate and question evidence resolved once for one run."""

    run_dir: Path
    artifact_roots: tuple[Path, ...]
    artifacts: dict[str, ArtifactResolution]

    def get(self, role: str) -> ArtifactResolution | None:
        return self.artifacts.get(role)

    def path(self, role: str) -> Path | None:
        resolved = self.get(role)
        return resolved.selected_path if resolved and resolved.usable else None


@dataclass(frozen=True)
class RuleContext:
    """Inputs visible to one pure business scorer."""

    question: QuestionProfile
    component: ComponentConfig
    artifacts: ArtifactBundle


@dataclass(frozen=True)
class CheckResult:
    """Canonical v4.13 leaf result on one implicit 0..100 scale."""

    check_id: str
    name: str
    score: float
    status: str
    reason_code: str
    explanation: str
    evidence: dict[str, Any] = field(default_factory=dict)
    prompt_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not math.isfinite(self.score) or not 0 <= self.score <= 100:
            raise ValueError(f"leaf score must be finite and in 0..100: {self.check_id}")

@dataclass(frozen=True)
class ComponentResult:
    """Diagnostic grouping and status for one component's leaf results."""

    question_id: str
    component: str
    checks: tuple[CheckResult, ...]
    status: str
    error: str = ""


@dataclass(frozen=True)
class RunScore:
    """Complete score for one candidate run before persistence."""

    question_id: str
    release: str
    artifacts: ArtifactBundle
    components: tuple[ComponentResult, ...]
    total_score: float | None
    status: str
    error: str = ""
    aggregates: tuple[Any, ...] = ()
