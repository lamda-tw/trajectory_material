"""Small contracts shared by the CLI application and capability providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RunRecord:
    run_dir: Path
    run_name: str
    task: str
    question: str
    model: str
    harness: str
    skill: str
    execution_key: tuple[str, str, str]
    metadata: dict[str, Any] = field(compare=False, hash=False, repr=False)

    @property
    def repeat_key(self) -> tuple[str, str, str, str, str]:
        return self.task, self.question, self.model, self.harness, self.skill

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_dir": self.run_dir.as_posix(),
            "run_name": self.run_name,
            "task": self.task,
            "question": self.question,
            "model": self.model,
            "harness": self.harness,
            "skill": self.skill,
            "execution_key": list(self.execution_key),
        }


@dataclass(frozen=True)
class SelectionGroup:
    repeat_key: tuple[str, str, str, str, str]
    members: tuple[RunRecord, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "repeat_key": list(self.repeat_key),
            "members": [value.as_dict() for value in self.members],
        }


@dataclass(frozen=True)
class SelectionPlan:
    repeat: str
    groups: tuple[SelectionGroup, ...]
    discovered_count: int
    filtered_count: int
    excluded: tuple[dict[str, str], ...] = ()

    @property
    def runs(self) -> tuple[RunRecord, ...]:
        return tuple(member for group in self.groups for member in group.members)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "eval-selection.v1",
            "repeat": self.repeat,
            "discovered_count": self.discovered_count,
            "filtered_count": self.filtered_count,
            "selected_run_count": len(self.runs),
            "group_count": len(self.groups),
            "groups": [value.as_dict() for value in self.groups],
            "excluded": list(self.excluded),
        }


@dataclass(frozen=True)
class ScorePackage:
    provider_id: str
    question: str
    status: str
    totals: tuple[tuple[str, float | None], ...]
    payload: dict[str, Any]

