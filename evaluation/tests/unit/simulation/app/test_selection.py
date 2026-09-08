import json
from pathlib import Path

from simulation.app.selection import SelectorSpec, load_selector, select_runs


QUESTION = "EI-56TESTPK-v1.2"


def _run(root: Path, *, model: str, serial: str, skill: str = "noskill") -> Path:
    run = root / f"{QUESTION}_codex_{model}_{skill}_{serial}"
    run.mkdir()
    (run / "run_metadata.json").write_text(
        json.dumps(
            {
                "question_version": QUESTION,
                "harness": "codex",
                "model": model,
                "skill_version": skill,
                "execution_date": f"2026-08-{serial[2:4]}",
                "execution_run": serial,
            }
        ),
        encoding="utf-8",
    )
    return run


def test_latest_and_average_share_the_same_fixed_repeat_key(tmp_path: Path) -> None:
    _run(tmp_path, model="gpt56", serial="0812A")
    latest = _run(tmp_path, model="gpt56", serial="0813A")
    _run(tmp_path, model="k3", serial="0812A")

    filters = {"task": ("EI",), "skill": ("noskill",)}
    latest_plan = select_runs(
        SelectorSpec((tmp_path,), filters, {}, "latest"), question_ids=(QUESTION,)
    )
    average_plan = select_runs(
        SelectorSpec((tmp_path,), filters, {}, "average"), question_ids=(QUESTION,)
    )

    assert len(latest_plan.groups) == 2
    assert len(latest_plan.runs) == 2
    assert next(group for group in latest_plan.groups if group.repeat_key[2] == "gpt56").members[0].run_dir == latest
    assert len(average_plan.runs) == 3


def test_selector_yaml_has_clear_include_exclude_and_repeat_semantics(tmp_path: Path) -> None:
    _run(tmp_path, model="gpt56", serial="0812A")
    _run(tmp_path, model="k3", serial="0812A")
    selector = tmp_path / "selector.yaml"
    selector.write_text(
        "\n".join(
            [
                "schema_version: '1.0'",
                "roots: ['.']",
                "include:",
                "  task: [EI]",
                "  model: ['*']",
                "exclude:",
                "  model: [k3]",
                "repeat: average",
                "",
            ]
        ),
        encoding="utf-8",
    )
    plan = select_runs(load_selector(selector), question_ids=(QUESTION,))
    assert plan.repeat == "average"
    assert [value.model for value in plan.runs] == ["gpt56"]


def test_dsh_and_sdk_are_parsed_as_harnesses_not_model_prefixes(tmp_path: Path) -> None:
    for harness in ("dsh", "sdk"):
        run = tmp_path / f"{QUESTION}_{harness}_dsv4f_noskill_0825A"
        run.mkdir()
        (run / "run_metadata.json").write_text(
            json.dumps(
                {
                    "question_version": QUESTION,
                    "harness": harness,
                    "model": "dsv4f",
                    "skill_version": "noskill",
                    "execution_date": "2026-08-25",
                    "execution_run": "0825A",
                }
            ),
            encoding="utf-8",
        )

    plan = select_runs(
        SelectorSpec((tmp_path,), {}, {}, "latest"), question_ids=(QUESTION,)
    )

    assert {(run.harness, run.model) for run in plan.runs} == {
        ("dsh", "dsv4f"),
        ("sdk", "dsv4f"),
    }
