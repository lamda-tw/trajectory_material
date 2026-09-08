from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def layout(base: Path, question_id: str = "Q") -> tuple[Path, Path, Path]:
    repo = base / "repo"
    question = repo / "evalsets" / "simulation" / question_id
    run = repo / "eval_results" / "run"
    question.mkdir(parents=True)
    (run / "project" / "model_output").mkdir(parents=True)
    return repo, question, run


def write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
    return path
