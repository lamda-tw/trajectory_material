from __future__ import annotations

from simulation.ei.core.adapters import resolve_artifacts

from evaluation.tests.helpers.simulation_adapter_factory import (
    build_layout,
    issue_codes,
    make_profile,
    write_csv_case,
)


def _wide_rows(week, inbound, outbound, inventory):
    return [
        ["2027M1", week, "Inbound", inbound, inbound],
        ["2027M1", week, "Outbound", outbound, outbound],
        ["2027M1", week, "Inventory", inventory, inventory],
    ]


def _resolve(tmp_path, headers, rows, *, raw_csv=None):
    repository, _, run = build_layout(tmp_path)
    relative = "56TESTPK/MaterialCycleEI/data-pipeline/model_output/weekly.csv"
    case = {"headers": headers, "rows": rows}
    if raw_csv is not None:
        case["raw_csv"] = raw_csv
    write_csv_case(run / relative, case)
    profile = make_profile(
        tmp_path,
        role="warehouse",
        schema="ei.warehouse",
        artifact_roots=("56TESTPK/MaterialCycleEI",),
        canonical_path=relative,
        filenames=("weekly.csv",),
        schema_options={"week_kind": "auto"},
    )
    return resolve_artifacts(profile, run, repository).get("warehouse")


def test_wide_ledger_derives_opening_from_the_immediately_previous_submitted_week(
    tmp_path,
) -> None:
    result = _resolve(
        tmp_path,
        ["month", "week", "type", "A", "total"],
        _wide_rows("WK1", 10, 3, 7) + _wide_rows("WK2", 2, 4, 5),
    )

    assert result.normalized[("a", 1)] == {
        "opening": 0,
        "inbound": 10,
        "outbound": 3,
        "closing": 7,
    }
    assert result.normalized[("a", 2)]["opening"] == 7


def test_wide_ledger_preserves_scope_and_region_in_the_business_key(tmp_path) -> None:
    headers = ["scope", "Region_ID", "month", "week", "type", "A", "total"]
    north = [["North", "R1", *row] for row in _wide_rows("WK1", 2, 1, 1)]
    south = [["South", "R1", *row] for row in _wide_rows("WK1", 3, 1, 2)]

    result = _resolve(tmp_path, headers, north + south)

    assert result.normalized[("scope=north", "region=r1", "a", 1)]["closing"] == 1
    assert result.normalized[("scope=south", "region=r1", "a", 1)]["closing"] == 2


def test_wide_ledger_supports_project_and_iso_week_dialects_without_conflation(
    tmp_path,
) -> None:
    result = _resolve(
        tmp_path,
        ["month", "week", "type", "A", "total"],
        _wide_rows("2027WK28", 1, 0, 1)
        + _wide_rows("2027-W29", 1, 0, 2),
    )

    assert ("a", 28) in result.normalized
    assert ("a", 202729) in result.normalized


def test_missing_and_duplicate_type_rows_are_diagnosed_instead_of_overwritten(
    tmp_path,
) -> None:
    missing = _resolve(
        tmp_path / "missing",
        ["month", "week", "type", "A", "total"],
        _wide_rows("WK1", 1, 0, 1)[:-1],
    )
    duplicated_rows = _wide_rows("WK1", 1, 0, 1)
    duplicated_rows.insert(1, list(duplicated_rows[0]))
    duplicated = _resolve(
        tmp_path / "duplicate",
        ["month", "week", "type", "A", "total"],
        duplicated_rows,
    )

    assert ("a", 1) not in missing.normalized
    assert "MISSING_TYPE" in issue_codes(missing)
    assert ("a", 1) not in duplicated.normalized
    assert "DUPLICATE_TYPE" in issue_codes(duplicated)


def test_fractional_quantity_is_retained_and_reported_without_rounding(tmp_path) -> None:
    result = _resolve(
        tmp_path,
        ["month", "week", "type", "A", "total"],
        _wide_rows("WK1", "1.5", 0, 1),
    )

    assert result.table.iloc[0]["A"] == "1.5"
    assert result.normalized[("a", 1)]["inbound"] == 1.5
    assert result.quantity_error_count == 1
    assert "NON_INTEGER_QUANTITY" in issue_codes(result)


def test_invalid_previous_week_does_not_get_silently_skipped_for_continuity(
    tmp_path,
) -> None:
    result = _resolve(
        tmp_path,
        ["month", "week", "type", "A", "total"],
        _wide_rows("WK1", 1, 0, 1)
        + _wide_rows("WK2", "bad", 0, 1)
        + _wide_rows("WK3", 0, 0, 1)
        + _wide_rows("WK4", 0, 0, 1),
    )

    assert ("a", 1) in result.normalized
    assert ("a", 2) not in result.normalized
    assert ("a", 3) not in result.normalized
    assert result.normalized[("a", 4)]["opening"] == 1
    issue = next(value for value in result.validation_issues if value["code"] == "UNVERIFIABLE_OPENING")
    assert issue["affected_unit_ids"] == ["wide:a:3"]


def test_exact_duplicate_material_headers_preserve_both_cells_and_other_materials(
    tmp_path,
) -> None:
    raw = (
        "month,week,type,A,A,B,total\n"
        "2027M1,2027-W27,Inbound,1,2,3,6\n"
        "2027M1,2027-W27,Outbound,0,0,1,1\n"
        "2027M1,2027-W27,Inventory,1,2,2,5\n"
    )
    result = _resolve(tmp_path, [], [], raw_csv=raw)

    assert tuple(result.table.attrs["source_headers"]) == (
        "month", "week", "type", "A", "A", "B", "total"
    )
    assert result.table.iloc[0, 3:5].tolist() == ["1", "2"]
    assert ("a", 202727) not in result.normalized
    assert result.normalized[("b", 202727)]["inbound"] == 3
    duplicate = next(value for value in result.validation_issues if value["code"] == "DUPLICATE_MATERIAL_COLUMN")
    assert duplicate["positions"] == [4, 5]


def test_long_ledger_preserves_dimensions_and_submitted_continuity_evidence(
    tmp_path,
) -> None:
    headers = [
        "scope", "Region", "item_code", "project_week",
        "opening", "inbound", "outbound", "closing",
    ]
    rows = [
        ["North", "R1", "A", "WK1", 0, 1, 0, 1],
        ["North", "R1", "A", "WK2", 1, "bad", 0, 5],
        ["North", "R1", "A", "WK3", 1, 0, 0, 1],
        ["South", "R1", "A", "WK1", 0, 3, 1, 2],
    ]

    result = _resolve(tmp_path, headers, rows)

    assert ("scope=north", "region=r1", "a", 2) not in result.normalized
    assert result.normalized[("scope=north", "region=r1", "a", 3)]["continuity_expected"] == 5
    assert result.normalized[("scope=south", "region=r1", "a", 1)]["closing"] == 2
