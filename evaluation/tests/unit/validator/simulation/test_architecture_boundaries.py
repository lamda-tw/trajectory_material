from __future__ import annotations

import inspect
import pkgutil
from dataclasses import fields
from importlib import import_module
from pathlib import Path

from simulation.ei.core.config import simulation_root
from simulation.ei.core.models import CheckResult, ComponentResult, RuleContext
from simulation.ei.rules.ei_standard import (
    common,
    effective_delivery,
    reuse,
    scheduling,
    simulation,
)


RULE_PACKAGES = (scheduling, effective_delivery, simulation, reuse)


def _rule_modules():
    yield common
    for package in RULE_PACKAGES:
        for info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
            yield import_module(info.name)


def test_ei_rules_do_not_open_or_discover_files() -> None:
    source = "\n".join(
        inspect.getsource(module) for module in _rule_modules()
    )

    for forbidden in (
        "pd.read_csv",
        "pd.read_excel",
        "pd.ExcelFile",
        ".rglob(",
        ".glob(",
        ".read_text(",
    ):
        assert forbidden not in source


def test_each_atomic_rule_has_one_source_module_and_one_mirrored_test_module() -> None:
    source_root = simulation_root() / "rules" / "ei_standard"
    test_root = Path(__file__).resolve().parent / "rules" / "ei_standard"
    expected = {
        "scheduling": ("c1", "c2", "c3", "c4", "c5", "c6a", "c6b", "o1"),
        "effective_delivery": ("o2",),
        "simulation": ("s1", "s2", "s3", "s4", "s5", "s6"),
        "reuse": ("r3", "r5", "r6"),
    }
    for family, rule_ids in expected.items():
        for rule_id in rule_ids:
            assert (source_root / family / f"{rule_id}.py").is_file()
            assert (test_root / family / f"test_{rule_id}.py").is_file()


def test_legacy_rule_god_files_and_flat_unit_tests_do_not_return() -> None:
    source_root = simulation_root() / "rules" / "ei_standard"
    for legacy in ("scheduling.py", "simulation.py", "reuse.py"):
        assert not (source_root / legacy).exists()
    unit_root = Path(__file__).resolve().parents[2]
    assert not list(unit_root.glob("test_*.py"))


def test_rule_context_contains_only_contract_data() -> None:
    assert {value.name for value in fields(RuleContext)} == {
        "question",
        "component",
        "artifacts",
    }


def test_rule_and_component_results_have_no_numeric_summary_contract() -> None:
    assert {value.name for value in fields(CheckResult)} == {
        "check_id",
        "name",
        "score",
        "status",
        "reason_code",
        "explanation",
        "evidence",
        "prompt_refs",
    }
    assert {value.name for value in fields(ComponentResult)} == {
        "question_id",
        "component",
        "checks",
        "status",
        "error",
    }


def test_rule_packages_do_not_depend_on_the_aggregation_layer() -> None:
    source = "\n".join(inspect.getsource(module) for module in _rule_modules())

    assert "simulation.ei.core.aggregation" not in source


def test_o2_does_not_call_or_import_the_legacy_five_rules() -> None:
    source = "\n".join(
        inspect.getsource(module)
        for module in _rule_modules()
        if ".effective_delivery" in module.__name__
    )

    for forbidden in (
        "score_c2",
        "score_c6a",
        "score_o1",
        "score_s1",
        "score_s5",
        "scheduling.c2",
        "scheduling.c6a",
        "scheduling.o1",
        "simulation.s1",
        "simulation.s5",
        "simulation.material",
        "scheduling.parsing",
    ):
        assert forbidden not in source


def test_o2_consumes_adapter_normalized_entities_without_raw_identification() -> None:
    source = "\n".join(
        inspect.getsource(module)
        for module in _rule_modules()
        if ".effective_delivery" in module.__name__
    )

    for forbidden in (
        "table(context",
        "_find_column",
        "_sheet_with",
        "read_csv",
        "read_excel",
        "ExcelFile",
    ):
        assert forbidden not in source
    assert "normalized(context" in source


def test_question_profiles_have_no_executable_rule_copies_or_dead_runtime_files() -> None:
    root = simulation_root()

    assert not list((root / "questions").rglob("*.py"))
    assert not list((root / "questions").rglob("simulation_config.json"))
    for legacy in (root / "readers", root / "runtime"):
        assert not legacy.exists() or not any(path.is_file() for path in legacy.rglob("*"))
