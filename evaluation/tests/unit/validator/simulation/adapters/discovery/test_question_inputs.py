from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep
from unittest.mock import patch

import pandas as pd

from simulation.ei.core.adapters import io
from simulation.ei.core.adapters import prepare_question_artifacts, resolve_artifacts

from evaluation.tests.helpers.simulation_adapter_factory import (
    build_layout,
    make_profile,
    write_csv_case,
)


def test_question_input_is_loaded_once_from_its_exact_contract_path(tmp_path) -> None:
    repository, question, run = build_layout(tmp_path)
    path = question / "data/input.csv"
    write_csv_case(path, {"headers": ["item_code"], "rows": [["A"]]})
    profile = make_profile(
        tmp_path,
        role="input",
        schema="generic",
        artifact_roots=("56TESTPK/MaterialCycleEI",),
        canonical_path="data/input.csv",
        filenames=(),
        source="question",
    )

    with patch.object(io, "read_table", wraps=io.read_table) as reader:
        result = resolve_artifacts(profile, run, repository).get("input")

    assert result.selected_path == path.resolve()
    assert result.status == "SELECTED_CANONICAL"
    assert reader.call_count == 1


def test_question_input_is_not_recovered_by_filename_from_another_directory(tmp_path) -> None:
    repository, question, run = build_layout(tmp_path)
    write_csv_case(
        question / "other/input.csv",
        {"headers": ["item_code"], "rows": [["A"]]},
    )
    profile = make_profile(
        tmp_path,
        role="input",
        schema="generic",
        artifact_roots=("56TESTPK/MaterialCycleEI",),
        canonical_path="data/input.csv",
        filenames=(),
        source="question",
    )

    result = resolve_artifacts(profile, run, repository).get("input")

    assert result.status == "MISSING"
    assert result.selected_path is None


def test_concurrent_question_cache_miss_loads_one_physical_table(tmp_path) -> None:
    io.clear_question_table_cache()
    path = str((tmp_path / "large.xlsx").resolve())
    calls = 0
    calls_lock = Lock()

    def fake_read_table(*_args, **_kwargs):
        nonlocal calls
        with calls_lock:
            calls += 1
        sleep(0.05)
        return pd.DataFrame({"value": [1]})

    try:
        with patch.object(io, "read_table", side_effect=fake_read_table):
            with ThreadPoolExecutor(max_workers=6) as executor:
                values = list(
                    executor.map(
                        lambda _index: io.read_question_table(path, "{}"),
                        range(6),
                    )
                )
    finally:
        io.clear_question_table_cache()

    assert calls == 1
    assert all(value is values[0] for value in values)


def test_prepared_question_resolution_skips_repeated_normalization(tmp_path) -> None:
    repository, question, run = build_layout(tmp_path)
    path = question / "data/input.csv"
    write_csv_case(path, {"headers": ["item_code"], "rows": [["A"]]})
    profile = make_profile(
        tmp_path,
        role="input",
        schema="generic",
        artifact_roots=("56TESTPK/MaterialCycleEI",),
        canonical_path="data/input.csv",
        filenames=(),
        source="question",
    )
    prepared = prepare_question_artifacts(profile, repository)

    from simulation.ei.core.adapters import _shared

    with patch.object(_shared, "_normalize_table", wraps=_shared._normalize_table) as normalize:
        result = resolve_artifacts(
            profile,
            run,
            repository,
            prepared_question_artifacts=prepared,
        ).get("input")

    assert normalize.call_count == 0
    assert result is prepared["input"]
