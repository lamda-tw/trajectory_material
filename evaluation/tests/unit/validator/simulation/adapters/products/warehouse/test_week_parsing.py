from __future__ import annotations

import pytest

from simulation.ei.core.adapters import parse_iso_week, parse_project_week


@pytest.mark.parametrize("value", [5, "5", "W5", "WK5", "wk5", "2027WK5", 67, "WK67"])
def test_observed_project_week_forms_are_equivalent(value) -> None:
    expected = 67 if "67" in str(value) else 5
    assert parse_project_week(value) == expected


@pytest.mark.parametrize("value", ["", "5.5", "WK0", "2023-W27"])
def test_ambiguous_or_out_of_range_project_weeks_fail(value) -> None:
    with pytest.raises(ValueError):
        parse_project_week(value)


def test_iso_week_is_validated_and_sortable_across_years() -> None:
    assert parse_iso_week("2023-W27") == 202327
    assert parse_iso_week("2023W27") == 202327
    assert parse_iso_week("2023-W52") < parse_iso_week("2024-W01")


@pytest.mark.parametrize("value", ["WK27", "2023-W00", "2023-W54", "2021-W53"])
def test_invalid_iso_week_fails(value) -> None:
    with pytest.raises(ValueError):
        parse_iso_week(value)
