from __future__ import annotations

from pathlib import Path

import pandas as pd

from simulation.ei.core.adapters import _shared
from simulation.ei.core.adapters.products import normalize_product
from simulation.ei.core.models import ArtifactSpec


def private(**values):
    return {"_effective_delivery": values}


def test_site_plan_has_stable_contract_and_dispatches_workbook_mapping() -> None:
    source = {
        "notes": pd.DataFrame({"comment": ["ignore"]}),
        "plan": pd.DataFrame(
            {
                "Site ID": ["S-1"],
                "Region/区域": ["R1"],
                "Action": ["install"],
                "week_num": [5],
                "mos_weekly_plan": ["WK5"],
                "week_start": ["2027-02-01"],
                "status": ["scheduled"],
                "site_count": [1],
                "cluster_id": ["C1"],
            }
        ),
    }

    normalized, issues = normalize_product(
        "site_plan",
        "ei.site-plan",
        source,
        private(o2_plan_mode="candidate-scheduled", o2_batch_kind="cluster"),
    )

    assert list(normalized.columns) == [
        "source_row",
        "site_id",
        "region",
        "action",
        "project_week",
        "week_num",
        "week_label",
        "week_start",
        "status",
        "site_count",
        "cluster_id",
        "mocn_batch_id",
    ]
    assert normalized.iloc[0].to_dict() == {
        "source_row": 2,
        "site_id": "S-1",
        "region": "R1",
        "action": "install",
        "project_week": "",
        "week_num": 5,
        "week_label": "WK5",
        "week_start": "2027-02-01",
        "status": "scheduled",
        "site_count": 1,
        "cluster_id": "C1",
        "mocn_batch_id": "",
    }
    assert normalized.attrs["source_sheet"] == "plan"
    assert issues == ()


def test_site_plan_required_fields_follow_the_question_contract() -> None:
    source = pd.DataFrame(
        {
            "site_name": ["S-1"],
            "site_action": ["install"],
            "mos_weekly_plan": ["2027WK5"],
            "week_num": [5],
            "region": ["R1"],
            "site_count": [1],
        }
    )

    normalized, issues = normalize_product(
        "site_plan",
        "ei.site-plan",
        source,
        private(
            o2_plan_mode="candidate-scheduled",
            o2_batch_kind="cluster",
            o2_site_plan_required_fields=[
                "site_id",
                "action",
                "week_label",
                "week_num",
                "region",
                "site_count",
            ],
        ),
    )

    assert normalized.loc[0, "week_start"] == ""
    assert normalized.loc[0, "status"] == ""
    assert normalized.loc[0, "cluster_id"] == ""
    assert not any(
        issue.get("code") == "MISSING_CANONICAL_COLUMN"
        for issue in issues
    )


def test_pk_site_plan_standardizes_compact_time_columns_without_guessing() -> None:
    source = pd.DataFrame(
        {
            "site_name": ["S-1", "S-2", "S-3", "S-4"],
            "site_action": ["install", "dismantle", "install", "install"],
            "mos_weekly_plan": ["2026WK2", "2027WK1", "WK3", "2027WK53"],
            "week_num": [2, 1, 3, 53],
            "region": ["R1", "R1", "R2", "R2"],
            "site_count": [1, 1, 1, 1],
        }
    )
    source_columns = source.columns.tolist()

    normalized, issues = normalize_product(
        "site_plan",
        "ei.site-plan",
        source,
        private(
            o2_plan_mode="candidate-scheduled",
            o2_batch_kind="mocn",
            o2_site_plan_required_fields=[
                "site_id",
                "region",
                "action",
                "project_week",
                "week_start",
            ],
        ),
    )

    assert normalized["project_week"].tolist() == [2, 1, 3, 53]
    assert normalized["week_start"].tolist() == [
        "2026-01-05",
        "2027-01-04",
        "",
        "",
    ]
    assert normalized["status"].tolist() == ["", "", "", ""]
    assert normalized["mocn_batch_id"].tolist() == ["", "", "", ""]
    assert source.columns.tolist() == source_columns
    assert issues == ()


def test_pk_site_plan_preserves_nonblank_explicit_time_values() -> None:
    source = pd.DataFrame(
        {
            "site_name": ["S-1", "S-2"],
            "region": ["R1", "R1"],
            "site_action": ["install", "dismantle"],
            "project_week": ["bad-week", ""],
            "week_num": [2, 3],
            "week_start": ["2026-01-06", ""],
            "mos_weekly_plan": ["2026WK2", "not-a-week"],
        }
    )

    normalized, issues = normalize_product(
        "site_plan",
        "ei.site-plan",
        source,
        private(
            o2_plan_mode="candidate-scheduled",
            o2_batch_kind="mocn",
            o2_site_plan_required_fields=[
                "site_id",
                "region",
                "action",
                "project_week",
                "week_start",
            ],
        ),
    )

    assert normalized["project_week"].tolist() == ["bad-week", 3]
    assert normalized["week_start"].tolist() == ["2026-01-06", ""]
    assert issues == ()


def test_site_plan_allows_authoritative_mocn_when_candidate_batch_is_optional(
) -> None:
    source = pd.DataFrame(
        {
            "site_name": ["S-1"],
            "site_action": ["install"],
            "mos_weekly_plan": ["2027WK5"],
            "week_num": [5],
            "region": ["R1"],
            "site_count": [1],
        }
    )

    normalized, issues = normalize_product(
        "site_plan",
        "ei.site-plan",
        source,
        private(
            o2_plan_mode="candidate-scheduled",
            o2_batch_kind="mocn",
            o2_site_plan_required_fields=[
                "site_id",
                "action",
                "week_label",
                "week_num",
                "region",
                "site_count",
            ],
        ),
    )

    assert normalized.loc[0, "mocn_batch_id"] == ""
    assert not any(
        issue.get("column") == "mocn_batch_id" for issue in issues
    )


def test_site_plan_normalizes_strict_short_week_num_to_integer() -> None:
    source = pd.DataFrame(
        {
            "site_name": ["S-1", "S-2"],
            "site_action": ["install", "install"],
            "mos_weekly_plan": ["2027WK21", "2027WK24"],
            "week_num": ["WK21", "WK24"],
            "region": ["R1", "R1"],
            "site_count": [1, 1],
        }
    )

    normalized, issues = normalize_product(
        "site_plan",
        "ei.site-plan",
        source,
        private(
            o2_site_plan_required_fields=[
                "site_id",
                "action",
                "week_label",
                "week_num",
                "region",
                "site_count",
            ],
        ),
    )

    assert normalized["week_num"].tolist() == [21, 24]
    assert issues == ()


def test_site_plan_qualifies_matching_short_week_label_for_single_year_o2() -> None:
    source = pd.DataFrame(
        {
            "site_name": ["S-1", "S-2"],
            "site_action": ["install", "dismantle"],
            "mos_weekly_plan": ["WK5", "wk7"],
            "week_num": [5, "WK7"],
            "region": ["R1", "R1"],
            "site_count": [1, 1],
        }
    )

    normalized, issues = normalize_product(
        "site_plan",
        "ei.site-plan",
        source,
        private(
            o2_planning_year=2027,
            o2_delivery_month_source="week-label",
            o2_project_week_source="reconcile",
            o2_site_plan_required_fields=[
                "site_id",
                "action",
                "week_label",
                "week_num",
                "region",
                "site_count",
            ],
        ),
    )

    assert normalized["week_num"].tolist() == [5, 7]
    assert normalized["week_label"].tolist() == ["2027WK5", "2027WK7"]
    assert issues == ()


def test_site_plan_does_not_qualify_short_week_label_for_week_num_mode() -> None:
    source = pd.DataFrame(
        {
            "site_name": ["S-1"],
            "site_action": ["install"],
            "mos_weekly_plan": ["WK5"],
            "week_num": [5],
            "region": ["R1"],
            "site_count": [1],
        }
    )

    normalized, issues = normalize_product(
        "site_plan",
        "ei.site-plan",
        source,
        private(
            o2_planning_year=2027,
            o2_delivery_month_source="week-label",
            o2_project_week_source="week_num",
            o2_site_plan_required_fields=[
                "site_id",
                "action",
                "week_label",
                "week_num",
                "region",
                "site_count",
            ],
        ),
    )

    assert normalized.loc[0, "week_label"] == "WK5"
    assert issues == ()

    normalized, issues = normalize_product(
        "site_plan",
        "ei.site-plan",
        source,
        private(
            o2_planning_year=2027,
            o2_delivery_month_source="schedule-week",
            o2_project_week_source="reconcile",
            o2_site_plan_required_fields=[
                "site_id",
                "action",
                "week_label",
                "week_num",
                "region",
                "site_count",
            ],
        ),
    )

    assert normalized.loc[0, "week_label"] == "WK5"
    assert issues == ()


def test_site_plan_does_not_qualify_ambiguous_or_invalid_short_week_label() -> None:
    source = pd.DataFrame(
        {
            "site_name": ["mismatch", "invalid-year-week", "not-strict"],
            "site_action": ["install", "install", "install"],
            "mos_weekly_plan": ["WK5", "WK53", "WK 7"],
            "week_num": [6, 53, 7],
            "region": ["R1", "R1", "R1"],
            "site_count": [1, 1, 1],
        }
    )

    normalized, issues = normalize_product(
        "site_plan",
        "ei.site-plan",
        source,
        private(
            o2_planning_year=2027,
            o2_delivery_month_source="week-label",
            o2_project_week_source="reconcile",
            o2_site_plan_required_fields=[
                "site_id",
                "action",
                "week_label",
                "week_num",
                "region",
                "site_count",
            ],
        ),
    )

    assert normalized["week_label"].tolist() == ["WK5", "WK53", "WK 7"]
    assert issues == ()


def test_site_plan_qualifies_valid_iso_week_53() -> None:
    source = pd.DataFrame(
        {
            "site_name": ["S-1"],
            "site_action": ["install"],
            "mos_weekly_plan": ["WK53"],
            "week_num": [53],
            "region": ["R1"],
            "site_count": [1],
        }
    )

    normalized, issues = normalize_product(
        "site_plan",
        "ei.site-plan",
        source,
        private(
            o2_planning_year=2026,
            o2_delivery_month_source="week-label",
            o2_project_week_source="reconcile",
            o2_site_plan_required_fields=[
                "site_id",
                "action",
                "week_label",
                "week_num",
                "region",
                "site_count",
            ],
        ),
    )

    assert normalized.loc[0, "week_label"] == "2026WK53"
    assert issues == ()


def test_site_plan_reports_only_configured_missing_fields_as_blocking() -> None:
    source = pd.DataFrame(
        {
            "site_name": ["S-1"],
            "site_action": ["install"],
            "project_week": [5],
            "region": ["R1"],
            "site_count": [1],
        }
    )

    _, issues = normalize_product(
        "site_plan",
        "ei.site-plan",
        source,
        private(
            o2_plan_mode="candidate-scheduled",
            o2_batch_kind="mocn",
            o2_site_plan_required_fields=[
                "site_id",
                "region",
                "action",
                "project_week",
                "week_start",
                "status",
                "site_count",
                "mocn_batch_id",
            ],
        ),
    )

    missing = {
        issue.get("column")
        for issue in issues
        if issue.get("code") == "MISSING_CANONICAL_COLUMN"
    }
    assert missing == {"week_start", "status", "mocn_batch_id"}


def test_final_material_derives_project_week_from_the_row_action() -> None:
    source = pd.DataFrame(
        {
            "site_name": ["S1", "S1"],
            "region": ["R1", "R1"],
            "action": ["install", "dismantle"],
            "item_code": ["I1", "I2"],
            "required_qty": [1, 1],
            "install_wk_label": ["WK7", "WK7"],
            "dismantle_wk_label": ["WK9", "WK9"],
            "install_month": [2, 2],
            "dismantle_month": [3, 3],
        }
    )

    normalized, issues = normalize_product(
        "final_material", "ei.final-material", source, {}
    )

    assert list(normalized["project_week"]) == [7, 9]
    assert list(normalized["install_week"]) == ["WK7", "WK7"]
    assert list(normalized["dismantle_week"]) == ["WK9", "WK9"]
    assert issues == ()


def test_scope_input_preserves_base_pk_band_and_ntnr() -> None:
    source = pd.DataFrame(
        {
            "*DU ID": ["S1"],
            "Region": ["R1"],
            "*物料编码": ["RRU5516"],
            "频段": ["1800"],
            "nTnR": ["4T4R"],
            "*数量": [2],
        }
    )

    normalized, issues = normalize_product(
        "scope_input",
        "generic",
        source,
        private(o2_scope_material_mode="base-pk-standardized"),
    )

    assert list(normalized.columns) == [
        "source_row",
        "site_id",
        "region",
        "item_code",
        "band",
        "ntnr",
        "action",
        "signed_quantity",
        "install_quantity",
        "redeploy_quantity",
        "dismantle_quantity",
    ]
    assert normalized.loc[0, ["site_id", "band", "ntnr", "signed_quantity"]].tolist() == [
        "S1",
        "1800",
        "4T4R",
        2,
    ]
    assert normalized.loc[
        0,
        ["install_quantity", "redeploy_quantity", "dismantle_quantity"],
    ].tolist() == ["", "", ""]
    assert issues == ()


def test_scope_input_does_not_reuse_one_signed_quantity_as_action_components() -> None:
    source = pd.DataFrame(
        {
            "*DU ID": ["S1", "S1"],
            "Region": ["R1", "R1"],
            "*物料编码": ["INSTALL", "DISMANTLE"],
            "*数量": [1, -2],
        }
    )

    normalized, issues = normalize_product(
        "scope_input",
        "generic",
        source,
        private(o2_scope_material_mode="raw"),
    )

    assert normalized["signed_quantity"].tolist() == [1, -2]
    assert normalized[
        ["install_quantity", "redeploy_quantity", "dismantle_quantity"]
    ].to_dict("records") == [
        {
            "install_quantity": "",
            "redeploy_quantity": "",
            "dismantle_quantity": "",
        },
        {
            "install_quantity": "",
            "redeploy_quantity": "",
            "dismantle_quantity": "",
        },
    ]
    assert issues == ()


def test_scope_input_does_not_reuse_action_quantity_as_signed_quantity() -> None:
    source = pd.DataFrame(
        {
            "SITE ID": ["S1"],
            "Region": ["R1"],
            "ITEM CODE": ["A"],
            "Installation Outbound/增加数量": [3],
            "Dismantling Inbound/减少数量": [2],
        }
    )

    normalized, issues = normalize_product(
        "scope_input",
        "generic",
        source,
        private(o2_scope_material_mode="raw"),
    )

    assert normalized.loc[
        0,
        ["signed_quantity", "install_quantity", "dismantle_quantity"],
    ].tolist() == ["", 3, 2]
    assert issues == ()


def test_master_plan_emits_period_and_preserves_explicit_source_years() -> None:
    long_source = pd.DataFrame(
        {
            "region": ["R1", "R1", "R1"],
            "site_type": ["macro", "macro", "macro"],
            "month": [2, "2028M3", pd.Timestamp("2029-04-01")],
            "master_count": [7, 8, 9],
        }
    )
    normalized, issues = normalize_product(
        "master_plan",
        "generic",
        long_source,
        private(o2_master_format="standard", o2_planning_year=2027),
    )
    assert normalized.to_dict("records") == [
        {
            "source_row": 2,
            "region": "R1",
            "site_type": "macro",
            "period": 202702,
            "month": 2,
            "planned_count": 7.0,
        },
        {
            "source_row": 3,
            "region": "R1",
            "site_type": "macro",
            "period": 202803,
            "month": 3,
            "planned_count": 8.0,
        },
        {
            "source_row": 4,
            "region": "R1",
            "site_type": "macro",
            "period": 202904,
            "month": 4,
            "planned_count": 9.0,
        },
    ]
    assert issues == ()


def test_master_plan_derives_the_install_curve_from_historical_site_actions() -> None:
    historical = pd.DataFrame(
        {
            "site_name": ["S1", "S2", "S3"],
            "site_action": ["install", "install", "dismantle"],
            "mos_weekly_plan": ["2027WK5", "2027WK6", "2027WK10"],
            "week_num": [5, 6, 10],
            "region": ["Region-1", "Region-1", "Region-2"],
            "site_count": [1, 1, 1],
        }
    )

    normalized, issues = normalize_product(
        "master_plan",
        "ei.site-plan",
        historical,
        private(o2_master_format="site-action-weekly-install"),
    )

    assert normalized.to_dict("records") == [
        {
            "source_row": 2,
            "region": "Region-1",
            "site_type": "install",
            "period": 202702,
            "month": 2,
            "planned_count": 1.0,
        },
        {
            "source_row": 3,
            "region": "Region-1",
            "site_type": "install",
            "period": 202702,
            "month": 2,
            "planned_count": 1.0,
        },
    ]
    assert issues == ()


def test_master_plan_pip_segments_select_the_first_numeric_summary_row() -> None:
    month_values = {
        "M1": [None, 999, "M1", None, 999, "M1", None, "M1", None],
        "M2": [102, 999, "M2", 202, 999, "M2", 302, "M2", 402],
        "M3": [103, 999, "M3", 203, 999, "M3", 303, "M3", 403],
        "M4": [104, 999, "M4", 204, 999, "M4", 304, "M4", 404],
        "M5": [105, 999, "M5", 205, 999, "M5", 305, "M5", 405],
        "M6": [106, 999, "M6", 206, 999, "M6", 306, "M6", 406],
        "M7": [107, 999, "M7", 207, 999, "M7", 307, "M7", 407],
    }
    wide_source = {
        "notes": pd.DataFrame({"text": ["ignore"]}),
        "City wise-PIP": pd.DataFrame(
            {
                "scope": [
                    "Region-1",
                    "detail",
                    "Region-2",
                    15,
                    "detail",
                    "Region-3",
                    9,
                    "Region-4",
                    6,
                ],
                **month_values,
            }
        ),
    }
    normalized, issues = normalize_product(
        "master_plan",
        "generic",
        wide_source,
        private(
            o2_master_format="pip-city-wise",
            o2_master_sheet_hint="City wise-PIP",
            o2_planning_year=2026,
            o2_project_start_month=11,
        ),
    )
    assert len(normalized) == 28
    assert normalized.groupby("region", sort=True).size().to_dict() == {
        "Region-1": 7,
        "Region-2": 7,
        "Region-3": 7,
        "Region-4": 7,
    }
    selected_rows = normalized.groupby("region", sort=True)["source_row"].unique()
    assert selected_rows.apply(list).to_dict() == {
        "Region-1": [2],
        "Region-2": [5],
        "Region-3": [8],
        "Region-4": [10],
    }
    region_two = normalized.loc[normalized["region"] == "Region-2"]
    assert region_two[["period", "month", "planned_count"]].to_dict("records") == [
        {"period": 202611, "month": 11, "planned_count": 0.0},
        {"period": 202612, "month": 12, "planned_count": 202.0},
        {"period": 202701, "month": 1, "planned_count": 203.0},
        {"period": 202702, "month": 2, "planned_count": 204.0},
        {"period": 202703, "month": 3, "planned_count": 205.0},
        {"period": 202704, "month": 4, "planned_count": 206.0},
        {"period": 202705, "month": 5, "planned_count": 207.0},
    ]
    assert normalized.attrs["source_sheet"] == "City wise-PIP"
    assert issues == ()


def test_master_plan_pip_promotes_embedded_pivot_header_before_sheet_selection() -> None:
    city_wise = pd.DataFrame(
        [
            ["Keep Site", 1, None, None, None],
            [None, None, None, None, None],
            ["行标签", "计数项:City", "M1", "M2", "M3"],
            ["Region-1", None, None, 102, 103],
            ["Region-2", None, "M1", "M2", "M3"],
            [15, None, None, 202, 203],
        ],
        columns=range(5),
    )
    _shared._attach_source_headers(
        city_wise,
        ["Top 17", "(空白)", "", "", ""],
    )
    site_level = pd.DataFrame(
        {
            "Vendor": ["Huawei"],
            "Site ID": ["S1"],
            "Region": ["Region-1"],
            "M2": [1],
            "M3": [1],
        }
    )

    normalized, issues = normalize_product(
        "master_plan",
        "generic",
        {
            "City wise-PIP": city_wise,
            "Site Level -PIP": site_level,
        },
        private(
            o2_master_format="pip-city-wise",
            o2_master_sheet_hint="",
            o2_planning_year=2026,
            o2_project_start_month=1,
        ),
    )

    assert normalized.attrs["source_sheet"] == "City wise-PIP"
    assert normalized.to_dict("records") == [
        {
            "source_row": 5,
            "region": "Region-1",
            "site_type": "",
            "period": 202601,
            "month": 1,
            "planned_count": 0.0,
        },
        {
            "source_row": 5,
            "region": "Region-1",
            "site_type": "",
            "period": 202602,
            "month": 2,
            "planned_count": 102.0,
        },
        {
            "source_row": 5,
            "region": "Region-1",
            "site_type": "",
            "period": 202603,
            "month": 3,
            "planned_count": 103.0,
        },
        {
            "source_row": 7,
            "region": "Region-2",
            "site_type": "",
            "period": 202601,
            "month": 1,
            "planned_count": 0.0,
        },
        {
            "source_row": 7,
            "region": "Region-2",
            "site_type": "",
            "period": 202602,
            "month": 2,
            "planned_count": 202.0,
        },
        {
            "source_row": 7,
            "region": "Region-2",
            "site_type": "",
            "period": 202603,
            "month": 3,
            "planned_count": 203.0,
        },
    ]
    assert issues == ()


def test_master_plan_matrix_uses_first_monthless_subheader_as_region() -> None:
    source = pd.DataFrame(
        {
            "Mouth/月份": [None, pd.Timestamp("2023-12-01"), pd.Timestamp("2024-01-01")],
            "Zone 1": ["BMA", 100, 200],
        }
    )

    normalized, issues = normalize_product(
        "master_plan",
        "generic",
        source,
        private(o2_master_format="standard", o2_planning_year=2027),
    )

    assert normalized.to_dict("records") == [
        {
            "source_row": 3,
            "region": "BMA",
            "site_type": "",
            "period": 202312,
            "month": 12,
            "planned_count": 100.0,
        },
        {
            "source_row": 4,
            "region": "BMA",
            "site_type": "",
            "period": 202401,
            "month": 1,
            "planned_count": 200.0,
        },
    ]
    assert issues == ()


def test_batch_input_uses_configured_batch_kind_to_select_sheet() -> None:
    source = {
        "mocn": pd.DataFrame({"site id": ["wrong"], "mocn_batch": [1]}),
        "cluster": pd.DataFrame(
            {"site id radio": ["S1"], "region": ["R1"], "cluster": ["C9"]}
        ),
    }

    normalized, issues = normalize_product(
        "batch_input", "generic", source, private(o2_batch_kind="cluster")
    )

    assert normalized.to_dict("records") == [
        {
            "source_row": 2,
            "site_id": "S1",
            "region": "R1",
            "cluster_id": "C9",
            "mocn_batch_id": "",
        }
    ]
    assert normalized.attrs["source_sheet"] == "cluster"
    assert issues == ()


def test_private_normalization_options_do_not_change_physical_read_options(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "artifact.csv"
    path.write_text("unused", encoding="utf-8")
    spec = ArtifactSpec(
        role="scope_input",
        source="question",
        path="artifact.csv",
        schema_options={"sheet_name": "Input4"},
    )
    captured: dict[str, object] = {}

    def fake_read_table(actual_path, actual_options):
        captured["read"] = (actual_path, actual_options)
        return pd.DataFrame({"site id": ["S1"], "item_code": ["I1"], "quantity": [1]})

    def fake_normalize(frame, role, schema, options):
        captured["normalize"] = options
        return frame.copy(), ()

    monkeypatch.setattr(
        "simulation.ei.core.adapters.io.read_table", fake_read_table
    )
    monkeypatch.setattr(_shared, "_normalize_table", fake_normalize)

    resolution = _shared._resolved_artifact(
        spec,
        path,
        status="SELECTED_CANONICAL",
        normalization_options={
            "sheet_name": "Input4",
            "_effective_delivery": {"o2_scope_material_mode": "raw"},
        },
    )

    assert resolution.usable
    assert captured["read"] == (path, {"sheet_name": "Input4"})
    assert captured["normalize"] == {
        "sheet_name": "Input4",
        "_effective_delivery": {"o2_scope_material_mode": "raw"},
    }
