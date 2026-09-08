"""Shared deterministic parsers used by the EI v4.12 business scorers."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import date
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from .batching import BatchLookup, compile_batch_lookup


def _norm(value: Any) -> str:
    if value is None:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    return re.sub(r"\s+", " ", str(value).strip())


def _key(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", _norm(value).casefold())


def _bom_key(value: Any) -> str:
    """Prompt-authorized BOM identity: trim and casefold only."""

    return _norm(value).casefold()


def _number(value: Any) -> float | None:
    if value is None or not _norm(value):
        return None
    try:
        result = float(str(value).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result / 100.0 if isinstance(value, str) and "%" in value else result


def _find_column(frame: pd.DataFrame, *candidates: str) -> str | None:
    aliases = {_key(value) for value in candidates}
    for column in frame.columns:
        if _key(column) in aliases:
            return str(column)
    for column in frame.columns:
        normalized = _key(column)
        if any(alias and alias in normalized for alias in aliases):
            return str(column)
    return None


def _sheet_with(
    source: pd.DataFrame | Mapping[str, pd.DataFrame],
    required_aliases: Sequence[Sequence[str]],
    *,
    sheet_hint: str = "",
) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        frames = (("", source),)
    elif isinstance(source, Mapping):
        ordered = sorted(
            source.items(),
            key=lambda value: (
                0 if sheet_hint and sheet_hint.casefold() in str(value[0]).casefold() else 1,
                str(value[0]).casefold(),
            ),
        )
        frames = tuple((str(name), frame) for name, frame in ordered)
    else:
        raise TypeError(f"unsupported in-memory question input: {type(source).__name__}")
    for _, frame in frames:
        if all(_find_column(frame, *aliases) is not None for aliases in required_aliases):
            return frame
    raise ValueError("no matching table in resolved question input")


def _expected_actions(
    source: pd.DataFrame | Mapping[str, pd.DataFrame],
    *,
    site_keyer: Callable[[Any], str] = _key,
) -> pd.DataFrame:
    raw = _sheet_with(
            source,
            (
                (
                    "site_name",
                    "site id",
                    "site id radio",
                    "站点",
                    "站点 id",
                    "*du id",
                    "du id",
                ),
                (
                    "required_qty",
                    "quantity",
                    "*数量",
                    "数量",
                    "installation outbound",
                    "dismantling inbound",
                    "new",
                    "redeploy",
                    "dismantle",
                ),
            ),
    )
    site_col = _find_column(
        raw,
        "site_name",
        "site id",
        "site id radio",
        "站点",
        "站点 id",
        "*du id",
        "du id",
    )
    region_col = _find_column(raw, "region", "区域")
    qty_col = _find_column(raw, "required_qty", "quantity", "*数量", "数量")
    install_col = _find_column(raw, "installation outbound", "增加数量", "new")
    redeploy_col = _find_column(raw, "redeploy")
    dismantle_col = _find_column(raw, "dismantling inbound", "减少数量", "dismantle")
    action_col = _find_column(raw, "action", "site_action")
    if site_col is None:
        raise ValueError("authoritative scope lacks site column")
    rows: list[dict[str, str]] = []
    for _, row in raw.iterrows():
        site = _norm(row.get(site_col))
        if not site:
            continue
        region = _norm(row.get(region_col)) if region_col else "ALL"
        actions: set[str] = set()
        if action_col:
            action = _norm(row.get(action_col)).casefold()
            if action in {"install", "dismantle"}:
                actions.add(action)
        if qty_col:
            quantity = _number(row.get(qty_col))
            if quantity is not None:
                actions.add("install" if quantity > 0 else "dismantle" if quantity < 0 else "")
        install_quantity = sum(
            value or 0.0
            for value in (
                _number(row.get(install_col)) if install_col else None,
                _number(row.get(redeploy_col)) if redeploy_col else None,
            )
        )
        if install_quantity > 0:
            actions.add("install")
        if dismantle_col and (_number(row.get(dismantle_col)) or 0.0) != 0:
            actions.add("dismantle")
        for action in actions - {""}:
            site_key = f"{_key(region)}|{site_keyer(site)}"
            rows.append(
                {
                    "site": site,
                    "region": region,
                    "action": action,
                    "site_key": site_key,
                    "action_key": f"{site_key}|{action}",
                }
            )
    result = pd.DataFrame(rows)
    if result.empty:
        raise ValueError("authoritative scope produced no site actions")
    return result.drop_duplicates("action_key")


def _month_number(value: Any) -> int | None:
    numeric = _number(value)
    if numeric is not None:
        return (
            int(numeric)
            if float(numeric).is_integer() and 1 <= numeric <= 12
            else None
        )
    label = _norm(value)
    match = re.fullmatch(
        r"(?:(?:20\d{2})\s*[-/]?\s*)?M(\d{1,2})",
        label,
        re.I,
    )
    if match:
        month = int(match.group(1))
        return month if 1 <= month <= 12 else None
    parsed = pd.to_datetime(value, errors="coerce")
    if not pd.isna(parsed):
        return int(parsed.month)
    return None


def _month_from_values(
    week_label: Any,
    week_value: Any,
    planning_year: int,
    *,
    week_to_month: str = "calendar",
    project_start_month: int = 1,
) -> int | None:
    """Resolve one month while keeping the historical row-level semantics."""

    label = _norm(week_label)
    parsed = pd.to_datetime(label, errors="coerce")
    if not pd.isna(parsed):
        return int(parsed.month)
    match = re.search(r"(?:(20\d{2})\D*)?(?:wk|w)(\d{1,2})", label, re.I)
    numeric_week = _number(week_value)
    week = int(match.group(2)) if match else int(numeric_week) if numeric_week is not None else None
    year = int(match.group(1)) if match and match.group(1) else planning_year
    if week is None or not 1 <= week <= 53:
        return None
    if week_to_month == "four-week-project":
        return project_start_month + (week - 1) // 4
    try:
        return date.fromisocalendar(year, week, 1).month
    except ValueError:
        return None


def _month_from_row(
    row: pd.Series,
    planning_year: int,
    *,
    week_to_month: str = "calendar",
    project_start_month: int = 1,
) -> int | None:
    return _month_from_values(
        row.get("week_label"),
        row.get("week"),
        planning_year,
        week_to_month=week_to_month,
        project_start_month=project_start_month,
    )


def _months_from_frame(
    frame: pd.DataFrame,
    planning_year: int,
    *,
    week_to_month: str = "calendar",
    project_start_month: int = 1,
) -> pd.Series:
    """Resolve month columns once per distinct week signature, not per row."""

    labels = (
        frame["week_label"].tolist()
        if "week_label" in frame
        else [""] * len(frame)
    )
    weeks = frame["week"].tolist() if "week" in frame else [""] * len(frame)
    cache: dict[tuple[str, str], int | None] = {}
    values: list[int | None] = []
    for label, week in zip(labels, weeks):
        signature = (_norm(label), _norm(week))
        if signature not in cache:
            cache[signature] = _month_from_values(
                label,
                week,
                planning_year,
                week_to_month=week_to_month,
                project_start_month=project_start_month,
            )
        values.append(cache[signature])
    return pd.Series(values, index=frame.index)


def _period_from_values(
    week_label: Any,
    week_value: Any,
    planning_year: int,
    *,
    week_to_month: str = "calendar",
    project_start_month: int = 1,
) -> int | None:
    """Resolve one natural-month ``YYYYMM`` coordinate without losing a year.

    Explicit dates and ISO-week labels retain their submitted year. Short week
    labels and numeric project weeks inherit the question's planning year. In
    four-week-project mode the project-month ordinal rolls across calendar
    years from the configured start month.
    """

    label = _norm(week_label)
    if week_to_month == "calendar":
        parsed = pd.to_datetime(label, errors="coerce")
        if not pd.isna(parsed):
            return int(parsed.year) * 100 + int(parsed.month)

    match = re.search(r"(?:(20\d{2})\D*)?(?:wk|w)(\d{1,2})", label, re.I)
    numeric_week = _number(week_value)
    week = (
        int(match.group(2))
        if match
        else int(numeric_week)
        if numeric_week is not None and float(numeric_week).is_integer()
        else None
    )
    if week is None or not 1 <= week <= 53:
        return None
    if week_to_month == "four-week-project":
        month_index = project_start_month + (week - 1) // 4
        zero_based = month_index - 1
        return (planning_year + zero_based // 12) * 100 + zero_based % 12 + 1

    year = int(match.group(1)) if match and match.group(1) else planning_year
    try:
        monday = date.fromisocalendar(year, week, 1)
    except ValueError:
        return None
    return monday.year * 100 + monday.month


def _periods_from_frame(
    frame: pd.DataFrame,
    planning_year: int,
    *,
    week_to_month: str = "calendar",
    project_start_month: int = 1,
) -> pd.Series:
    """Resolve year-qualified periods once per distinct week signature."""

    labels = (
        frame["week_label"].tolist()
        if "week_label" in frame
        else [""] * len(frame)
    )
    weeks = frame["week"].tolist() if "week" in frame else [""] * len(frame)
    cache: dict[tuple[str, str], int | None] = {}
    values: list[int | None] = []
    for label, week in zip(labels, weeks):
        signature = (_norm(label), _norm(week))
        if signature not in cache:
            cache[signature] = _period_from_values(
                label,
                week,
                planning_year,
                week_to_month=week_to_month,
                project_start_month=project_start_month,
            )
        values.append(cache[signature])
    return pd.Series(values, index=frame.index)


def _master_plan(
    source: pd.DataFrame | Mapping[str, pd.DataFrame],
    *,
    sheet_hint: str = "",
    planning_year: int,
    master_format: str = "standard",
) -> tuple[dict[tuple[str, int], float], dict[int, float]]:
    if master_format == "pip-city-wise":
        raw = _sheet_with(source, (("M1", "month", "月份"),), sheet_hint=sheet_hint)
    elif isinstance(source, pd.DataFrame):
        raw = source
    else:
        frames = sorted(
            source.items(),
            key=lambda value: (
                0 if sheet_hint and sheet_hint.casefold() in str(value[0]).casefold() else 1,
                str(value[0]).casefold(),
            ),
        )
        raw = next(
            (
                candidate
                for _, candidate in frames
                if _find_column(candidate, "month", "月份", "安装/拆除月份")
                or any(re.fullmatch(r"M\d+", _norm(column), re.I) for column in candidate.columns)
            ),
            pd.DataFrame(),
        )
        if raw.empty:
            raise ValueError("authoritative master plan table not found")
    month_col = _find_column(raw, "month", "月份", "安装/拆除月份")
    region_col = _find_column(raw, "region", "区域")
    count_col = _find_column(
        raw,
        "master_count",
        "planned_count",
        "count",
        "site_count",
    )
    by_region: dict[tuple[str, int], float] = defaultdict(float)
    project_columns = [
        (str(column), int(match.group(1)))
        for column in raw.columns
        if (match := re.fullmatch(r"M(\d{1,2})", _norm(column), re.I))
    ]
    if master_format == "pip-city-wise" and project_columns:
        scope_col = str(raw.columns[0])
        for _, row in raw.iterrows():
            scope = _norm(row.get(scope_col))
            if not re.fullmatch(r"(?:region|zone)[- ]?\d+", scope, re.I):
                continue
            for column, month in project_columns:
                value = _number(row.get(column))
                if value is not None:
                    by_region[(_key(scope), month)] += value
    elif month_col and count_col:
        for _, row in raw.iterrows():
            month = _month_number(row.get(month_col))
            if month is not None:
                by_region[(_key(row.get(region_col) if region_col else "ALL"), month)] += _number(row.get(count_col)) or 0.0
    elif month_col:
        for _, row in raw.iterrows():
            month = _month_number(row.get(month_col))
            if month is None:
                continue
            for column in raw.columns:
                if str(column) == month_col:
                    continue
                value = _number(row.get(column))
                if value is not None:
                    by_region[(_key(column), month)] += value
    else:
        for column, month in project_columns:
            values = raw[column].map(_number)
            by_region[("all", month)] += float(
                sum(1 for value in values if value not in (None, 0.0))
            )
    if not by_region:
        raise ValueError("authoritative master plan produced no month quantities")
    totals: dict[int, float] = defaultdict(float)
    for (_, month), value in by_region.items():
        totals[month] += value
    return dict(by_region), dict(totals)


def _delivery_batches(
    source: pd.DataFrame | Mapping[str, pd.DataFrame],
    *,
    batch_kind: str,
) -> tuple[BatchLookup, list[dict[str, Any]]]:
    """Read the Prompt-authorized site-to-delivery-batch relationship.

    A delivery batch is a Cluster for Cluster-based questions and a MOCN batch
    for MOCN-based questions. Keeping the type explicit prevents either
    business object from being silently interpreted as the other.
    """

    if batch_kind == "cluster":
        batch_aliases = (
            "cluster",
            "cluster_id",
            "cluster id",
            "cluster/簇",
            "簇",
        )
    elif batch_kind == "mocn":
        batch_aliases = (
            "mocn_batch",
            "mocn batch",
            "mocn batch id",
            "mocn开通批次",
            "mocn批次号",
            "batch_id",
        )
    else:
        raise ValueError(f"unsupported delivery batch kind: {batch_kind}")

    site_aliases = (
        "site id",
        "site id radio",
        "site_name",
        "site name",
        "站点",
        "du id",
        "*du id",
    )
    raw = _sheet_with(source, (site_aliases, batch_aliases))
    site_col = _find_column(raw, *site_aliases)
    region_col = _find_column(raw, "region", "区域")
    batch_col = _find_column(raw, *batch_aliases)
    if site_col is None or batch_col is None:
        raise ValueError(f"delivery batch input lacks site/{batch_kind} columns")

    mapping: dict[str, str] = {}
    batch_rows: list[dict[str, Any]] = []
    seen_batches: set[tuple[str, str]] = set()
    for source_order, (_, row) in enumerate(raw.iterrows()):
        site = _norm(row.get(site_col))
        batch = _norm(row.get(batch_col))
        region = _norm(row.get(region_col)) if region_col else "ALL"
        if not site or not batch:
            continue
        mapping[f"{_key(region)}|{_key(site)}"] = batch
        batch_identity = (_key(region), batch)
        if batch_identity not in seen_batches:
            seen_batches.add(batch_identity)
            batch_rows.append(
                {
                    "batch": batch,
                    "region": region,
                    "source_order": source_order,
                }
            )
    return compile_batch_lookup(mapping), batch_rows


def _quantity_overlap(
    expected: Mapping[Any, float],
    actual: Mapping[Any, float],
) -> tuple[float, dict[str, Any]]:
    keys = set(expected) | set(actual)
    matched = sum(
        min(max(0.0, expected.get(key, 0.0)), max(0.0, actual.get(key, 0.0)))
        for key in keys
    )
    combined = sum(
        max(max(0.0, expected.get(key, 0.0)), max(0.0, actual.get(key, 0.0)))
        for key in keys
    )
    return (matched / combined if combined else 1.0), {
        "objects": len(keys),
        "matched_qty": round(matched, 6),
        "combined_qty": round(combined, 6),
    }


def _substitution_roles(
    source: pd.DataFrame | Mapping[str, pd.DataFrame],
    *,
    mode: str,
) -> dict[str, set[str]]:
    """Compile target-specific actual-code roles from the resolved Prompt source."""

    if isinstance(source, pd.DataFrame) and _find_column(source, "target_item_code"):
        target_col = _find_column(source, "target_item_code")
        sub_col = _find_column(source, "sub_item_code")
        new_col = _find_column(source, "new_issue_item_code")
        if target_col is None or sub_col is None:
            raise ValueError("substitution source lacks target/sub role columns")
        roles: dict[str, set[str]] = defaultdict(set)
        current = ""
        for _, row in source.iterrows():
            target = _bom_key(row.get(target_col))
            if target:
                current = target
                roles.setdefault(current, set())
            if not current:
                continue
            for column in (sub_col, new_col):
                actual = _bom_key(row.get(column)) if column else ""
                if actual and actual != current:
                    roles[current].add(actual)
        if not roles:
            raise ValueError("substitution source produced no target views")
        return {
            target: {actual for actual in actuals if actual != target}
            for target, actuals in roles.items()
        }

    raw = (
        source
        if isinstance(source, pd.DataFrame)
        else next(
            (frame for name, frame in source.items() if str(name).casefold() == "pcp0101"),
            None,
        )
    )
    if raw is None:
        raise ValueError("resolved substitution source lacks PCP0101")
    groups: dict[str, list[tuple[int, str]]] = defaultdict(list)
    body = raw.fillna("").iloc[2:]
    if len(body.columns):
        body = body.loc[body.iloc[:, 0].map(_norm).ne("")]
    for _, row in body.iterrows():
        group = _norm(row.iloc[0] if len(row) else "")
        priority = _number(row.iloc[1] if len(row) > 1 else "")
        if not group or priority is None:
            continue
        item = next(
            (
                _bom_key(row.iloc[index])
                for index in (2, 6, 10)
                if len(row) > index and _norm(row.iloc[index])
            ),
            "",
        )
        if item:
            groups[group].append((int(priority), item))
    if not groups:
        raise ValueError("Input5 PCP0101 produced no substitution roles")
    roles: dict[str, set[str]] = defaultdict(set)
    for rows in groups.values():
        ordered = [item for _, item in sorted(rows)]
        if len(ordered) < 2:
            continue
        roles[ordered[0]].update(ordered[1:])
        if mode == "expanded-bidirectional":
            intermediates = ordered[1:-1]
            fallback = ordered[-1]
            for target in intermediates:
                roles[target].update(
                    item for item in (*intermediates, fallback) if item != target
                )
    if not roles:
        raise ValueError("substitution source produced no target views")
    return {
        target: {actual for actual in actuals if actual != target}
        for target, actuals in roles.items()
    }


def _structured_legacy_views(
    source: pd.DataFrame,
) -> dict[tuple[str, int], dict[str, Any]]:
    """Normalize legacy rows by semantic target, not arbitrary solution_id."""

    solution_col = _find_column(source, "solution_id")
    priority_col = _find_column(source, "priority")
    target_col = _find_column(source, "target_item_code")
    target_qty_col = _find_column(source, "target_qty")
    sub_col = _find_column(source, "sub_item_code")
    sub_qty_col = _find_column(source, "sub_qty")
    new_col = _find_column(source, "new_issue_item_code")
    if None in {
        solution_col,
        priority_col,
        target_col,
        target_qty_col,
        sub_col,
        sub_qty_col,
    }:
        raise ValueError("structured substitution source lacks quantity fields")

    parsed: list[dict[str, Any]] = []
    solution_targets: dict[str, tuple[str, int]] = {}
    for _, row in source.iterrows():
        solution = re.sub(
            r"_p\d+$",
            "",
            _norm(row.get(solution_col)).casefold(),
        )
        priority_value = _number(row.get(priority_col))
        if (
            not solution
            or priority_value is None
            or not float(priority_value).is_integer()
            or int(priority_value) <= 0
        ):
            raise ValueError(
                "solution_id and a positive integer priority are required"
            )
        target = _bom_key(row.get(target_col))
        target_quantity_value = _number(row.get(target_qty_col))
        if target:
            if (
                target_quantity_value is None
                or not float(target_quantity_value).is_integer()
                or int(target_quantity_value) <= 0
            ):
                raise ValueError("target_qty must be a positive integer")
            target_fact = (target, int(target_quantity_value))
            if solution in solution_targets and solution_targets[solution] != target_fact:
                raise ValueError("target conflicts within one legacy solution")
            solution_targets[solution] = target_fact
        parsed.append(
            {
                "solution": solution,
                "priority": int(priority_value),
                "target": target,
                "target_quantity": (
                    int(target_quantity_value)
                    if target
                    else None
                ),
                "item": _bom_key(row.get(sub_col)),
                "quantity": _number(row.get(sub_qty_col)),
                "fallback": _bom_key(row.get(new_col)) if new_col else "",
            }
        )

    views: dict[tuple[str, int], dict[str, Any]] = {}
    active_occurrence: dict[str, int] = {}
    occurrence_counts: dict[str, int] = defaultdict(int)
    inferred_occurrences: dict[tuple[str, str], int] = {}
    for value in parsed:
        target = value["target"]
        target_quantity = value["target_quantity"]
        if not target:
            target_fact = solution_targets.get(value["solution"])
            if target_fact is None:
                raise ValueError(
                    "legacy substitution row cannot be linked to a target"
                )
            target, target_quantity = target_fact
        if int(value["priority"]) == 1:
            occurrence_counts[target] += 1
            active_occurrence[target] = occurrence_counts[target]
        occurrence = active_occurrence.get(target)
        if occurrence is None:
            inferred_key = (str(value["solution"]), target)
            occurrence = inferred_occurrences.get(inferred_key)
            if occurrence is None:
                occurrence_counts[target] += 1
                occurrence = occurrence_counts[target]
                inferred_occurrences[inferred_key] = occurrence
        view = views.setdefault(
            (target, occurrence),
            {
                "target": target,
                "target_quantity": int(target_quantity),
                "levels": defaultdict(list),
                "fallbacks": set(),
            },
        )
        if int(view["target_quantity"]) != int(target_quantity):
            raise ValueError("target_qty conflicts for one legacy target")
        item = value["item"]
        if item:
            quantity_value = value["quantity"]
            if (
                quantity_value is None
                or not float(quantity_value).is_integer()
                or int(quantity_value) <= 0
            ):
                raise ValueError(
                    "substitution quantity must be a positive integer"
                )
            material = (item, int(quantity_value))
            level = view["levels"][int(value["priority"])]
            if material not in level:
                level.append(material)
        if value["fallback"]:
            view["fallbacks"].add(value["fallback"])
    if not views:
        raise ValueError("structured substitution source produced no target views")
    return views


def _partition_expanded_source_levels(
    ordered: list[tuple[int, tuple[tuple[str, int], ...]]],
    *,
    fallback_requires_new_prefix: bool,
) -> tuple[
    list[tuple[int, tuple[tuple[str, int], ...]]],
    tuple[tuple[str, int], ...] | None,
]:
    """Split Input5 intermediate levels from its optional new-issue fallback."""

    final_bundle = ordered[-1][1]
    has_new_fallback = not fallback_requires_new_prefix or (
        len(final_bundle) == 1 and final_bundle[0][0].startswith("new_")
    )
    if has_new_fallback:
        return ordered[1:-1], final_bundle
    return ordered[1:], None


def _substitution_alternatives(
    source: pd.DataFrame | Mapping[str, pd.DataFrame],
    *,
    mode: str,
    fallback_requires_new_prefix: bool = False,
) -> dict[str, tuple[tuple[int, tuple[tuple[str, int], ...]], ...]]:
    """Compile Prompt Input5 into target-specific quantity-preserving bundles."""

    if (
        isinstance(source, pd.DataFrame)
        and _find_column(source, "target_item_code")
        and mode in {"legacy-combination", "legacy-target-fallback"}
    ):
        views = _structured_legacy_views(source)
        combined: dict[
            str,
            set[tuple[int, tuple[tuple[str, int], ...]]],
        ] = defaultdict(set)
        for view in views.values():
            target = str(view["target"])
            target_quantity = int(view["target_quantity"])
            alternatives: set[
                tuple[int, tuple[tuple[str, int], ...]]
            ] = set()
            for priority, values in view["levels"].items():
                bundle = tuple(sorted(values))
                is_identity_target_row = (
                    int(priority) == 1
                    and bundle == ((target, target_quantity),)
                )
                if is_identity_target_row and mode != "legacy-target-fallback":
                    continue
                if bundle:
                    alternatives.add((target_quantity, bundle))
            if alternatives:
                combined[target].update(alternatives)
        structured = {
            target: tuple(sorted(alternatives))
            for target, alternatives in combined.items()
            if alternatives
        }
        if not structured:
            raise ValueError("structured substitution source produced no alternatives")
        return structured

    if isinstance(source, pd.DataFrame) and _find_column(source, "target_item_code"):
        solution_col = _find_column(source, "solution_id")
        priority_col = _find_column(source, "priority")
        target_col = _find_column(source, "target_item_code")
        target_qty_col = _find_column(source, "target_qty")
        sub_col = _find_column(source, "sub_item_code")
        sub_qty_col = _find_column(source, "sub_qty")
        new_col = _find_column(source, "new_issue_item_code")
        if None in {
            solution_col,
            priority_col,
            target_col,
            target_qty_col,
            sub_col,
            sub_qty_col,
        }:
            raise ValueError("structured substitution source lacks quantity fields")
        views: dict[
            tuple[str, str],
            dict[str, Any],
        ] = {}
        current_target = ""
        current_target_quantity: int | None = None
        current_solution = ""
        current_priority: int | None = None
        for row_index, row in source.iterrows():
            target = _bom_key(row.get(target_col))
            solution = _norm(row.get(solution_col)).casefold()
            priority_value = _number(row.get(priority_col))
            target_quantity_value = _number(row.get(target_qty_col))
            if target:
                if (
                    target_quantity_value is None
                    or not float(target_quantity_value).is_integer()
                    or int(target_quantity_value) <= 0
                ):
                    raise ValueError("target_qty must be a positive integer")
                current_target = target
                current_target_quantity = int(target_quantity_value)
            if solution:
                # Prompt Input5 encodes priority rows as ``..._P1``, ``..._P2``,
                # etc.  Those rows are one solution view, not independent views.
                current_solution = re.sub(r"_p\d+$", "", solution)
            if priority_value is not None:
                if not float(priority_value).is_integer():
                    raise ValueError("priority must be an integer")
                current_priority = int(priority_value)
            if (
                not current_target
                or current_target_quantity is None
                or not current_solution
                or current_priority is None
            ):
                continue
            view_key = (current_target, current_solution)
            view = views.setdefault(
                view_key,
                {
                    "target_quantity": current_target_quantity,
                    "levels": defaultdict(list),
                    "fallbacks": set(),
                    "rows": [],
                },
            )
            if target:
                if current_target_quantity != int(view["target_quantity"]):
                    raise ValueError("target_qty conflicts within one solution view")
            view["rows"].append(int(row_index) + 2)
            item = _bom_key(row.get(sub_col))
            if item:
                quantity_value = _number(row.get(sub_qty_col))
                if (
                    quantity_value is None
                    or not float(quantity_value).is_integer()
                    or int(quantity_value) <= 0
                ):
                    raise ValueError("substitution quantity must be a positive integer")
                view["levels"][current_priority].append((item, int(quantity_value)))
            fallback = _bom_key(row.get(new_col)) if new_col else ""
            if fallback and fallback != current_target:
                view["fallbacks"].add(fallback)
        if not views:
            raise ValueError("structured substitution source produced no alternatives")
        by_target: dict[str, list[set[tuple[int, tuple[tuple[str, int], ...]]]]] = defaultdict(list)
        for (target, _), view in views.items():
            target_quantity = int(view["target_quantity"])
            if target_quantity <= 0:
                raise ValueError("target_qty must be a positive integer")
            alternatives: set[tuple[int, tuple[tuple[str, int], ...]]] = set()
            for bundle in view["levels"].values():
                if bundle:
                    alternatives.add((target_quantity, tuple(sorted(bundle))))
            explicit_items = {
                item
                for bundle in view["levels"].values()
                for item, _ in bundle
            }
            for fallback in view["fallbacks"]:
                if fallback not in explicit_items:
                    alternatives.add((target_quantity, ((fallback, target_quantity),)))
            if alternatives:
                by_target[target].append(alternatives)
        structured: dict[str, tuple[tuple[int, tuple[tuple[str, int], ...]], ...]] = {}
        for target, alternatives_by_view in by_target.items():
            combined: set[tuple[int, tuple[tuple[str, int], ...]]] = set()
            for alternatives in alternatives_by_view:
                combined.update(alternatives)
            structured[target] = tuple(sorted(combined))
        if not structured:
            raise ValueError("structured substitution source produced no legal alternatives")
        return structured

    raw = (
        source
        if isinstance(source, pd.DataFrame)
        else next(
            (frame for name, frame in source.items() if str(name).casefold() == "pcp0101"),
            None,
        )
    )
    if raw is None:
        raise ValueError("resolved substitution source lacks PCP0101")
    groups: dict[str, dict[int, list[tuple[str, int]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    body = raw.fillna("").iloc[2:]
    if len(body.columns):
        body = body.loc[body.iloc[:, 0].map(_norm).ne("")]
    for _, row in body.iterrows():
        group = _norm(row.iloc[0] if len(row) else "")
        priority_value = _number(row.iloc[1] if len(row) > 1 else "")
        if not group or priority_value is None or not float(priority_value).is_integer():
            continue
        priority = int(priority_value)
        slots = ((2, 5),) if mode == "expanded-bidirectional" else (
            (2, 5),
            (6, 9),
            (10, 13),
        )
        for item_index, quantity_index in slots:
            item = _bom_key(row.iloc[item_index] if len(row) > item_index else "")
            quantity_value = _number(
                row.iloc[quantity_index] if len(row) > quantity_index else ""
            )
            if not item:
                continue
            if (
                quantity_value is None
                or not float(quantity_value).is_integer()
                or int(quantity_value) <= 0
            ):
                raise ValueError("Input5 substitution quantities must be positive integers")
            groups[group][priority].append((item, int(quantity_value)))
    if not groups:
        raise ValueError("Input5 PCP0101 produced no substitution alternatives")

    output: dict[str, list[tuple[int, tuple[tuple[str, int], ...]]]] = defaultdict(list)
    for levels in groups.values():
        ordered = [
            (priority, tuple(values))
            for priority, values in sorted(levels.items())
            if values
        ]
        if len(ordered) < 2:
            continue
        original_item, original_quantity = ordered[0][1][0]
        if mode == "legacy-target-fallback":
            output[original_item].append(
                (original_quantity, ((original_item, original_quantity),))
            )
        for _, bundle in ordered[1:]:
            output[original_item].append((original_quantity, bundle))
        if mode == "expanded-bidirectional":
            intermediate_levels, fallback = _partition_expanded_source_levels(
                ordered,
                fallback_requires_new_prefix=fallback_requires_new_prefix,
            )
            intermediate = [
                (item, quantity)
                for _, bundle in intermediate_levels
                for item, quantity in bundle
            ]
            for target_index, (target, target_quantity) in enumerate(intermediate):
                for item_index, (item, quantity) in enumerate(intermediate):
                    if item_index != target_index:
                        output[target].append(
                            (target_quantity, ((item, quantity),))
                        )
                if fallback is not None:
                    output[target].append((target_quantity, fallback))
    normalized: dict[str, tuple[tuple[int, tuple[tuple[str, int], ...]], ...]] = {}
    for target, alternatives in output.items():
        unique = {
            (
                target_quantity,
                tuple(sorted(bundle)),
            )
            for target_quantity, bundle in alternatives
            if bundle
        }
        if unique:
            normalized[target] = tuple(sorted(unique))
    if not normalized:
        raise ValueError("Input5 produced no legal target alternatives")
    return normalized


def _substitution_relation_objects(
    source: pd.DataFrame | Mapping[str, pd.DataFrame],
    *,
    mode: str,
    fallback_requires_new_prefix: bool = False,
) -> set[
    tuple[
        str,
        str,
        str,
        int,
        int,
        tuple[tuple[str, int], ...],
        str,
    ]
]:
    """Compile directed, priority-aware replacement relations for S1 Jaccard.

    Each object keeps group, target-view identity, target, target quantity,
    priority, bundle, and role. Target-view identity preserves Prompt Tk when
    two source rows happen to use the same item code. Same-priority rows stay
    together as an AND bundle; priorities remain separate OR alternatives.
    """

    if mode not in {
        "legacy-combination",
        "legacy-target-fallback",
        "expanded-bidirectional",
        "priority-row-views",
    }:
        raise ValueError(f"unsupported substitution mode: {mode}")

    if isinstance(source, pd.DataFrame) and _find_column(source, "target_item_code"):
        solution_col = _find_column(source, "solution_id")
        priority_col = _find_column(source, "priority")
        target_col = _find_column(source, "target_item_code")
        target_qty_col = _find_column(source, "target_qty")
        sub_col = _find_column(source, "sub_item_code")
        sub_qty_col = _find_column(source, "sub_qty")
        new_col = _find_column(source, "new_issue_item_code")
        if None in {
            solution_col,
            priority_col,
            target_col,
            target_qty_col,
            sub_col,
            sub_qty_col,
        }:
            raise ValueError("structured substitution source lacks relation fields")

        if mode in {"legacy-combination", "legacy-target-fallback"}:
            legacy_views = _structured_legacy_views(source)
            legacy_relations: set[
                tuple[
                    str,
                    str,
                    str,
                    int,
                    int,
                    tuple[tuple[str, int], ...],
                    str,
                ]
            ] = set()
            for view in legacy_views.values():
                target = str(view["target"])
                target_quantity = int(view["target_quantity"])
                fallbacks = set(view["fallbacks"])
                if len(fallbacks) > 1:
                    raise ValueError(
                        "new_issue_item_code conflicts for one legacy target"
                    )
                fallback = next(iter(fallbacks), "")
                levels = [
                    (int(priority), tuple(sorted(values)))
                    for priority, values in sorted(view["levels"].items())
                    if values
                ]
                if not levels:
                    continue
                final_priority = levels[-1][0]
                for priority, bundle in levels:
                    identity_target_row = (
                        priority == 1
                        and bundle == ((target, target_quantity),)
                    )
                    if identity_target_row and mode != "legacy-target-fallback":
                        continue
                    if mode == "legacy-target-fallback":
                        role = "fallback" if identity_target_row else "substitute"
                    elif fallback:
                        role = (
                            "fallback"
                            if priority == final_priority
                            and len(bundle) == 1
                            and bundle[0][0] == fallback
                            else "substitute"
                        )
                    else:
                        role = (
                            "fallback"
                            if priority == final_priority
                            else "substitute"
                        )
                    legacy_relations.add(
                        (
                            target,
                            "t1",
                            target,
                            target_quantity,
                            priority,
                            bundle,
                            role,
                        )
                    )
            if not legacy_relations:
                raise ValueError(
                    "structured substitution source produced no relations"
                )
            return legacy_relations

        views: dict[tuple[str, str], dict[str, Any]] = {}
        for _, row in source.iterrows():
            solution = _norm(row.get(solution_col)).casefold()
            priority_value = _number(row.get(priority_col))
            if (
                not solution
                or priority_value is None
                or not float(priority_value).is_integer()
                or int(priority_value) <= 0
            ):
                raise ValueError(
                    "solution_id and a positive integer priority are required"
                )
            priority = int(priority_value)
            if mode == "expanded-bidirectional":
                match = re.fullmatch(
                    r"(?P<group>.+)_t(?P<view>\d+)_p(?P<position>\d+)",
                    solution,
                )
                if match is None:
                    raise ValueError(
                        "expanded substitution solution_id must use {Group}_Tk_Pm"
                    )
                if int(match.group("position")) != priority:
                    raise ValueError(
                        "solution_id Pm must equal the priority column"
                    )
                group = _norm(match.group("group")).casefold()
                target_view = f"t{int(match.group('view'))}"
            else:
                group = re.sub(r"_p\d+$", "", solution)
                target_view = "t1"
            if not group:
                raise ValueError("substitution group cannot be empty")

            view = views.setdefault(
                (group, target_view),
                {
                    "target": "",
                    "target_quantity": None,
                    "levels": defaultdict(list),
                    "fallbacks": set(),
                },
            )
            target = _bom_key(row.get(target_col))
            target_quantity_value = _number(row.get(target_qty_col))
            if target:
                if (
                    target_quantity_value is None
                    or not float(target_quantity_value).is_integer()
                    or int(target_quantity_value) <= 0
                ):
                    raise ValueError("target_qty must be a positive integer")
                target_quantity = int(target_quantity_value)
                if view["target"] and view["target"] != target:
                    raise ValueError("target item conflicts within one target view")
                if (
                    view["target_quantity"] is not None
                    and int(view["target_quantity"]) != target_quantity
                ):
                    raise ValueError("target_qty conflicts within one target view")
                view["target"] = target
                view["target_quantity"] = target_quantity

            item = _bom_key(row.get(sub_col))
            if item:
                quantity_value = _number(row.get(sub_qty_col))
                if (
                    quantity_value is None
                    or not float(quantity_value).is_integer()
                    or int(quantity_value) <= 0
                ):
                    raise ValueError(
                        "substitution quantity must be a positive integer"
                    )
                view["levels"][priority].append((item, int(quantity_value)))
            fallback = _bom_key(row.get(new_col)) if new_col else ""
            if fallback:
                view["fallbacks"].add(fallback)

        relations: set[
            tuple[
                str,
                str,
                str,
                int,
                int,
                tuple[tuple[str, int], ...],
                str,
            ]
        ] = set()
        for (group, target_view), view in views.items():
            target = str(view["target"])
            target_quantity = view["target_quantity"]
            if not target or target_quantity is None:
                raise ValueError("each target view requires its P1 target row")
            fallbacks = set(view["fallbacks"])
            if len(fallbacks) > 1:
                raise ValueError(
                    "new_issue_item_code conflicts within one target view"
                )
            fallback = next(iter(fallbacks), "")
            levels: list[tuple[int, tuple[tuple[str, int], ...]]] = []
            for priority, values in sorted(view["levels"].items()):
                bundle = tuple(sorted(values))
                if (
                    mode == "legacy-combination"
                    and priority == 1
                    and bundle == ((target, int(target_quantity)),)
                ):
                    continue
                if bundle:
                    levels.append((int(priority), bundle))
            if not levels:
                continue
            final_priority = levels[-1][0]
            for priority, bundle in levels:
                role = (
                    "fallback"
                    if priority == final_priority
                    and fallback
                    and len(bundle) == 1
                    and bundle[0][0] == fallback
                    else "substitute"
                )
                relations.add(
                    (
                        group,
                        target_view,
                        target,
                        int(target_quantity),
                        priority,
                        bundle,
                        role,
                    )
                )
        if not relations:
            raise ValueError("structured substitution source produced no relations")
        return relations

    raw = (
        source
        if isinstance(source, pd.DataFrame)
        else next(
            (
                frame
                for name, frame in source.items()
                if str(name).casefold() == "pcp0101"
            ),
            None,
        )
    )
    if raw is None:
        raise ValueError("resolved substitution source lacks PCP0101")
    groups: dict[str, dict[int, list[tuple[str, int]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    body = raw.fillna("").iloc[2:]
    if len(body.columns):
        body = body.loc[body.iloc[:, 0].map(_norm).ne("")]
    for _, row in body.iterrows():
        group = _norm(row.iloc[0] if len(row) else "").casefold()
        priority_value = _number(row.iloc[1] if len(row) > 1 else "")
        if (
            not group
            or priority_value is None
            or not float(priority_value).is_integer()
        ):
            continue
        priority = int(priority_value)
        slots = (
            ((2, 5),)
            if mode == "expanded-bidirectional"
            else ((2, 5), (6, 9), (10, 13))
        )
        for item_index, quantity_index in slots:
            item = _bom_key(
                row.iloc[item_index] if len(row) > item_index else ""
            )
            quantity_value = _number(
                row.iloc[quantity_index] if len(row) > quantity_index else ""
            )
            if not item:
                continue
            if (
                quantity_value is None
                or not float(quantity_value).is_integer()
                or int(quantity_value) <= 0
            ):
                raise ValueError(
                    "Input5 substitution quantities must be positive integers"
                )
            groups[group][priority].append((item, int(quantity_value)))
    if not groups:
        raise ValueError("Input5 PCP0101 produced no substitution relations")

    relations: set[
        tuple[
            str,
            str,
            str,
            int,
            int,
            tuple[tuple[str, int], ...],
            str,
        ]
    ] = set()
    for group, levels in groups.items():
        ordered = [
            (priority, tuple(sorted(values)))
            for priority, values in sorted(levels.items())
            if values
        ]
        if len(ordered) < 2:
            continue
        target, target_quantity = ordered[0][1][0]
        object_group = group if mode == "expanded-bidirectional" else target
        if mode == "legacy-target-fallback":
            relations.add(
                (
                    object_group,
                    "t1",
                    target,
                    target_quantity,
                    int(ordered[0][0]),
                    ((target, target_quantity),),
                    "fallback",
                )
            )
        expanded_intermediates: list[
            tuple[int, tuple[tuple[str, int], ...]]
        ] = []
        expanded_fallback: tuple[tuple[str, int], ...] | None = None
        if mode == "expanded-bidirectional":
            expanded_intermediates, expanded_fallback = (
                _partition_expanded_source_levels(
                    ordered,
                    fallback_requires_new_prefix=fallback_requires_new_prefix,
                )
            )
        alternatives = ordered[1:]
        for index, (priority, bundle) in enumerate(alternatives):
            relations.add(
                (
                    object_group,
                    "t1",
                    target,
                    target_quantity,
                    priority,
                    bundle,
                    (
                        "fallback"
                        if mode != "legacy-target-fallback"
                        and index == len(alternatives) - 1
                        and (
                            mode != "expanded-bidirectional"
                            or expanded_fallback is not None
                        )
                        else "substitute"
                    ),
                )
            )
        if mode == "expanded-bidirectional":
            for target_index, (_, target_bundle) in enumerate(
                expanded_intermediates
            ):
                intermediate_target, intermediate_quantity = target_bundle[0]
                view_alternatives = [
                    other_bundle
                    for other_index, (_, other_bundle) in enumerate(
                        expanded_intermediates
                    )
                    if other_index != target_index
                ]
                if expanded_fallback is not None:
                    view_alternatives.append(expanded_fallback)
                for offset, bundle in enumerate(view_alternatives, start=2):
                    relations.add(
                        (
                            group,
                            f"t{target_index + 2}",
                            intermediate_target,
                            intermediate_quantity,
                            offset,
                            tuple(sorted(bundle)),
                            (
                                "fallback"
                                if expanded_fallback is not None
                                and offset == len(view_alternatives) + 1
                                else "substitute"
                            ),
                        )
                    )
    if not relations:
        raise ValueError("Input5 produced no legal directed substitution relations")
    return relations


def _compile_candidate_substitution(
    source: pd.DataFrame | Mapping[str, pd.DataFrame],
    *,
    mode: str,
) -> dict[str, Any]:
    """Compile candidate relations without discarding unrelated valid views.

    The Prompt authority is intentionally compiled by the strict public helpers
    above.  Candidate output uses this compiler so a malformed row/view becomes
    a Jaccard omission/extra instead of invalidating the complete artifact.
    Relations and final-BOM alternatives are emitted from the same normalized
    candidate views.
    """

    if mode not in {
        "legacy-combination",
        "legacy-target-fallback",
        "expanded-bidirectional",
        "priority-row-views",
    }:
        raise ValueError(f"unsupported substitution mode: {mode}")

    def alternatives_from_relations(
        relations: set[
            tuple[
                str,
                str,
                str,
                int,
                int,
                tuple[tuple[str, int], ...],
                str,
            ]
        ],
    ) -> dict[str, tuple[tuple[int, tuple[tuple[str, int], ...]], ...]]:
        projected: dict[
            str,
            set[tuple[int, tuple[tuple[str, int], ...]]],
        ] = defaultdict(set)
        for _, _, target, target_quantity, _, bundle, _ in relations:
            if bundle:
                projected[target].add((target_quantity, bundle))
        return {
            target: tuple(sorted(alternatives))
            for target, alternatives in sorted(projected.items())
            if alternatives
        }

    if not isinstance(source, pd.DataFrame):
        # Candidate material_substitution is a structured table.  Keep this
        # compatibility path for callers that explicitly pass Prompt Input5.
        relations = _substitution_relation_objects(source, mode=mode)
        return {
            "relations": relations,
            "alternatives": alternatives_from_relations(relations),
            "issues": [],
        }

    solution_col = _find_column(source, "solution_id")
    priority_col = _find_column(source, "priority")
    target_col = _find_column(source, "target_item_code")
    target_qty_col = _find_column(source, "target_qty")
    sub_col = _find_column(source, "sub_item_code")
    sub_qty_col = _find_column(source, "sub_qty")
    new_col = _find_column(source, "new_issue_item_code")
    if None in {
        solution_col,
        priority_col,
        target_col,
        target_qty_col,
        sub_col,
        sub_qty_col,
    }:
        raise ValueError("structured substitution source lacks relation fields")

    # Preserve the exact historical relation objects for a fully valid table.
    # P_apply is deliberately projected from those same objects instead of
    # independently reparsing the candidate table.
    try:
        strict_relations = _substitution_relation_objects(source, mode=mode)
    except ValueError:
        pass
    else:
        return {
            "relations": strict_relations,
            "alternatives": alternatives_from_relations(strict_relations),
            "issues": [],
        }

    issue_views: dict[str, dict[str, set[Any]]] = {}

    def record_issue(view: str, code: str, rows: Sequence[int] = ()) -> None:
        key = view or "<unlinked>"
        issue = issue_views.setdefault(
            key,
            {"codes": set(), "rows": set()},
        )
        issue["codes"].add(code)
        issue["rows"].update(int(value) for value in rows)

    records: list[dict[str, Any]] = []
    legacy_potential_anchors: dict[str, set[tuple[str, int]]] = defaultdict(set)
    for row_number, (_, row) in enumerate(source.iterrows(), start=2):
        raw_solution = _norm(row.get(solution_col)).casefold()
        priority_value = _number(row.get(priority_col))
        provisional_view = raw_solution or f"row:{row_number}"
        if (
            not raw_solution
            or priority_value is None
            or not float(priority_value).is_integer()
            or int(priority_value) <= 0
        ):
            record_issue(
                provisional_view,
                "INVALID_SOLUTION_OR_PRIORITY",
                (row_number,),
            )
            continue
        priority = int(priority_value)

        target = _bom_key(row.get(target_col))
        target_quantity_value = _number(row.get(target_qty_col))
        target_fact: tuple[str, int] | None = None
        if target:
            if (
                target_quantity_value is None
                or not float(target_quantity_value).is_integer()
                or int(target_quantity_value) <= 0
            ):
                record_issue(
                    provisional_view,
                    "INVALID_TARGET_QUANTITY",
                    (row_number,),
                )
                continue
            target_fact = (target, int(target_quantity_value))

        item = _bom_key(row.get(sub_col))
        quantity_value = _number(row.get(sub_qty_col))
        invalid_material = bool(item) and (
            quantity_value is None
            or not float(quantity_value).is_integer()
            or int(quantity_value) <= 0
        )
        fallback = _bom_key(row.get(new_col)) if new_col else ""
        record: dict[str, Any] = {
            "row": row_number,
            "raw_solution": raw_solution,
            "priority": priority,
            "target_fact": target_fact,
            "item": item,
            "quantity": (
                int(quantity_value)
                if item and not invalid_material and quantity_value is not None
                else None
            ),
            "invalid_material": invalid_material,
            "fallback": fallback,
        }

        if mode in {"legacy-combination", "legacy-target-fallback"}:
            standard_solution = re.sub(r"_p\d+$", "", raw_solution)
            numeric_match = re.fullmatch(r"(?P<base>.+)_(?P<position>\d+)", raw_solution)
            numeric_base = ""
            if (
                standard_solution == raw_solution
                and numeric_match is not None
                and int(numeric_match.group("position")) == priority
            ):
                numeric_base = _norm(numeric_match.group("base")).casefold()
            anchor_key = numeric_base or standard_solution
            if target_fact is not None:
                legacy_potential_anchors[anchor_key].add(target_fact)
            record.update(
                {
                    "standard_solution": standard_solution,
                    "numeric_base": numeric_base,
                }
            )
        elif mode == "expanded-bidirectional":
            match = re.fullmatch(
                r"(?P<group>.+)_t(?P<view>\d+)_p(?P<position>\d+)",
                raw_solution,
            )
            if match is None:
                record_issue(
                    provisional_view,
                    "UNLINKED_SOLUTION_ID",
                    (row_number,),
                )
                continue
            group = _norm(match.group("group")).casefold()
            target_view = f"t{int(match.group('view'))}"
            view_name = f"{group}:{target_view}"
            if int(match.group("position")) != priority:
                record_issue(
                    view_name,
                    "SOLUTION_PRIORITY_MISMATCH",
                    (row_number,),
                )
            record.update({"group": group, "target_view": target_view})
        else:
            group = re.sub(r"_p\d+$", "", raw_solution)
            if not group:
                record_issue(
                    provisional_view,
                    "UNLINKED_SOLUTION_ID",
                    (row_number,),
                )
                continue
            record.update({"group": group, "target_view": "t1"})
        records.append(record)

    if mode in {"legacy-combination", "legacy-target-fallback"}:
        for record in records:
            numeric_base = str(record.get("numeric_base", ""))
            if (
                numeric_base
                and len(legacy_potential_anchors.get(numeric_base, set())) == 1
            ):
                record["solution"] = numeric_base
            else:
                record["solution"] = str(record["standard_solution"])

    anchors: dict[Any, set[tuple[str, int]]] = defaultdict(set)
    anchor_rows: dict[Any, list[int]] = defaultdict(list)

    def family_name(family: Any) -> str:
        if isinstance(family, tuple) and len(family) == 2:
            return f"{family[0]}:{family[1]}"
        return str(family)

    for record in records:
        family = (
            str(record["solution"])
            if mode in {"legacy-combination", "legacy-target-fallback"}
            else (str(record["group"]), str(record["target_view"]))
        )
        record["family"] = family
        if record["target_fact"] is not None:
            anchors[family].add(record["target_fact"])
            anchor_rows[family].append(int(record["row"]))
    for family, facts in anchors.items():
        if len(facts) > 1:
            record_issue(
                family_name(family),
                "TARGET_FACT_CONFLICT",
                anchor_rows[family],
            )

    linked: list[dict[str, Any]] = []
    for record in records:
        target_fact = record["target_fact"]
        family_facts = anchors.get(record["family"], set())
        if len(family_facts) > 1:
            # Nothing in a conflicting family can be assigned to one
            # authoritative target view without choosing an arbitrary winner.
            continue
        if target_fact is None:
            if len(family_facts) != 1:
                record_issue(
                    family_name(record["family"]),
                    (
                        "AMBIGUOUS_TARGET_LINK"
                        if family_facts
                        else "UNLINKED_TARGET"
                    ),
                    (int(record["row"]),),
                )
                continue
            target_fact = next(iter(family_facts))
        record["target"], record["target_quantity"] = target_fact
        linked.append(record)

    views: dict[Any, dict[str, Any]] = {}
    if mode in {"legacy-combination", "legacy-target-fallback"}:
        occurrence_counts: dict[str, int] = defaultdict(int)
        active_occurrence: dict[str, int] = {}
        inferred_occurrences: dict[tuple[str, str, int], int] = {}
        occurrence_quantities: dict[tuple[str, int], set[int]] = defaultdict(set)
        for record in linked:
            target = str(record["target"])
            target_quantity = int(record["target_quantity"])
            if int(record["priority"]) == 1:
                occurrence_counts[target] += 1
                active_occurrence[target] = occurrence_counts[target]
            occurrence = active_occurrence.get(target)
            if occurrence is None:
                inferred_key = (
                    str(record["solution"]),
                    target,
                    target_quantity,
                )
                occurrence = inferred_occurrences.get(inferred_key)
                if occurrence is None:
                    occurrence_counts[target] += 1
                    occurrence = occurrence_counts[target]
                    inferred_occurrences[inferred_key] = occurrence
            occurrence_key = (target, occurrence)
            occurrence_quantities[occurrence_key].add(target_quantity)
            view_key = (target, occurrence, target_quantity)
            record["compiled_view"] = view_key
            views.setdefault(
                view_key,
                {
                    "name": f"{target}:t1:{occurrence}",
                    "group": target,
                    "target_view": "t1",
                    "target": target,
                    "target_quantity": target_quantity,
                    "levels": defaultdict(list),
                    "fallbacks": set(),
                    "fallback_rows": [],
                    "invalid_priorities": set(),
                    "rows": [],
                },
            )
        for occurrence_key, quantities in occurrence_quantities.items():
            if len(quantities) > 1:
                rows = [
                    int(value["row"])
                    for value in linked
                    if (
                        str(value["target"]),
                        value["compiled_view"][1],
                    )
                    == occurrence_key
                ]
                record_issue(
                    f"{occurrence_key[0]}:t1:{occurrence_key[1]}",
                    "TARGET_QUANTITY_CONFLICT",
                    rows,
                )
                for view_key, view in views.items():
                    if view_key[:2] == occurrence_key:
                        view["invalid_target"] = True
    else:
        for record in linked:
            target = str(record["target"])
            target_quantity = int(record["target_quantity"])
            view_key = (
                record["family"],
                target,
                target_quantity,
            )
            record["compiled_view"] = view_key
            group, target_view = record["family"]
            views.setdefault(
                view_key,
                {
                    "name": f"{group}:{target_view}",
                    "group": str(group),
                    "target_view": str(target_view),
                    "target": target,
                    "target_quantity": target_quantity,
                    "levels": defaultdict(list),
                    "fallbacks": set(),
                    "fallback_rows": [],
                    "invalid_priorities": set(),
                    "rows": [],
                },
            )

    for record in linked:
        view = views[record["compiled_view"]]
        row_number = int(record["row"])
        priority = int(record["priority"])
        view["rows"].append(row_number)
        if record["invalid_material"]:
            view["invalid_priorities"].add(priority)
            record_issue(
                str(view["name"]),
                "INVALID_SUBSTITUTION_QUANTITY",
                (row_number,),
            )
        elif record["item"]:
            material = (str(record["item"]), int(record["quantity"]))
            level = view["levels"][priority]
            if mode in {"legacy-combination", "legacy-target-fallback"}:
                if material not in level:
                    level.append(material)
            else:
                level.append(material)
        if record["fallback"]:
            view["fallbacks"].add(str(record["fallback"]))
            view["fallback_rows"].append(row_number)

    relations: set[
        tuple[
            str,
            str,
            str,
            int,
            int,
            tuple[tuple[str, int], ...],
            str,
        ]
    ] = set()
    for view in views.values():
        if bool(view.get("invalid_target", False)):
            continue
        target = str(view["target"])
        target_quantity = int(view["target_quantity"])
        invalid_priorities = set(view["invalid_priorities"])
        fallbacks = set(view["fallbacks"])
        fallback_conflict = len(fallbacks) > 1
        if fallback_conflict:
            record_issue(
                str(view["name"]),
                "NEW_ISSUE_CONFLICT",
                view["fallback_rows"],
            )
        fallback = next(iter(fallbacks), "") if not fallback_conflict else ""
        levels = [
            (int(priority), tuple(sorted(values)))
            for priority, values in sorted(view["levels"].items())
            if values and int(priority) not in invalid_priorities
        ]
        final_priority = levels[-1][0] if levels else None
        for priority, bundle in levels:
            identity_target_row = (
                priority == 1
                and bundle == ((target, target_quantity),)
            )
            if identity_target_row and mode == "legacy-combination":
                continue
            if mode == "legacy-target-fallback":
                role = "fallback" if identity_target_row else "substitute"
            elif fallback_conflict:
                if len(bundle) == 1 and bundle[0][0] in fallbacks:
                    # The material alternative is explicit, but its relation
                    # role is not deterministic while new_issue conflicts.
                    continue
                role = "substitute"
            elif mode == "legacy-combination" and not fallback:
                role = "fallback" if priority == final_priority else "substitute"
            else:
                role = (
                    "fallback"
                    if priority == final_priority
                    and fallback
                    and len(bundle) == 1
                    and bundle[0][0] == fallback
                    else "substitute"
                )
            relations.add(
                (
                    str(view["group"]),
                    str(view["target_view"]),
                    target,
                    target_quantity,
                    priority,
                    bundle,
                    role,
                )
            )

    issues = [
        {
            "view": view,
            "codes": sorted(str(value) for value in issue["codes"]),
            "rows": sorted(int(value) for value in issue["rows"])[:20],
        }
        for view, issue in sorted(issue_views.items())
    ]
    if not relations and not issues:
        issues = [
            {
                "view": "<table>",
                "codes": ["NO_DETERMINATE_RELATIONS"],
                "rows": [],
            }
        ]
    return {
        "relations": relations,
        "alternatives": alternatives_from_relations(relations),
        "issues": issues,
    }




def _base_pk_material_code(
    item_value: Any,
    band_value: Any,
    ntnr_value: Any,
) -> str:
    """Apply the base PK Prompt's four-class material standardization."""

    item = _norm(item_value)
    item_key = item.casefold()
    if item_key.startswith("ubbp"):
        return "ubbp"

    band = _norm(band_value)
    band_tokens = re.findall(r"(?<!\d)(\d{3,4})(?!\d)", band)
    if not band_tokens or all(int(value) == 0 for value in band_tokens):
        return ""
    ntnr = re.sub(r"[^0-9a-z]+", "_", _norm(ntnr_value).casefold()).strip("_")
    if not ntnr:
        return ""

    if "rru5516" in item_key:
        normalized_band = "_".join(dict.fromkeys(band_tokens))
        return f"rru5516_{normalized_band}_{ntnr}"

    def is_multiband(value: Any) -> bool:
        text = _norm(value).casefold()
        if re.search(
            r"\d{3,4}\s*m?\s*[&/+，,]\s*\d{3,4}",
            text,
        ):
            return True
        fragments = re.split(r"[&/+，,]", text)
        return sum(
            bool(re.search(r"(?<!\d)\d{3,4}(?!\d)", fragment))
            for fragment in fragments
        ) >= 2

    for frequency in ("900", "1800"):
        if (
            "rru" in item_key
            and re.search(rf"(?<!\d){frequency}\s*m(?!\d)", item_key)
            and not is_multiband(item)
            and not is_multiband(band)
            and len(band_tokens) == 1
            and band_tokens[0] == frequency
        ):
            return f"rru{frequency}_{frequency}_{ntnr}"
    return ""


def _base_pk_scope_material_facts(
    frame: pd.DataFrame,
    *,
    site_keyer: Callable[[Any], str] = _key,
) -> dict[str, dict[str, int]]:
    site_col = _find_column(frame, "*DU ID", "site_name", "site id")
    region_col = _find_column(frame, "Region", "region")
    item_col = _find_column(frame, "*物料编码", "item_code", "item code")
    band_col = _find_column(frame, "频段", "band")
    ntnr_col = _find_column(frame, "nTnR", "ntnr")
    quantity_col = _find_column(frame, "*数量", "required_qty", "quantity")
    if None in {
        site_col,
        region_col,
        item_col,
        band_col,
        ntnr_col,
        quantity_col,
    }:
        raise ValueError("base PK scope input lacks Prompt material fields")

    positions = frame.columns.get_indexer(
        [site_col, region_col, item_col, band_col, ntnr_col, quantity_col]
    )
    output: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in frame.itertuples(index=False, name=None):
        site = _norm(row[int(positions[0])])
        region = _norm(row[int(positions[1])])
        if not site:
            continue
        quantity_value = _number(row[int(positions[5])])
        if quantity_value is None or float(quantity_value) == 0:
            continue
        if not float(quantity_value).is_integer():
            raise ValueError("base PK scope quantities must be integers")
        item = _base_pk_material_code(
            row[int(positions[2])],
            row[int(positions[3])],
            row[int(positions[4])],
        )
        if not item:
            continue
        quantity = int(quantity_value)
        action = "install" if quantity > 0 else "dismantle"
        action_key = f"{_key(region)}|{site_keyer(site)}|{action}"
        output[action_key][item] += quantity
    return {
        action_key: {
            item: quantity
            for item, quantity in materials.items()
            if quantity != 0
        }
        for action_key, materials in output.items()
        if any(quantity != 0 for quantity in materials.values())
    }


def _scope_material_facts(
    source: pd.DataFrame | Mapping[str, pd.DataFrame],
    *,
    material_mode: str = "raw",
    site_keyer: Callable[[Any], str] = _key,
) -> dict[str, dict[str, int]]:
    """Compile the Prompt Input4 variants to site-action original BOM facts."""

    frames = [source] if isinstance(source, pd.DataFrame) else list(source.values())
    frame = next(
        (
            value
            for value in frames
            if _find_column(
                value,
                "site id",
                "*du id",
                "*du id 站点 id",
                "site id radio/站点",
            )
            and _find_column(value, "*物料编码", "item code", "item_code", "*bom/编码")
        ),
        None,
    )
    if frame is None:
        raise ValueError("scope input lacks the Prompt Input4 site/BOM sheet")
    if material_mode == "base-pk-standardized":
        return _base_pk_scope_material_facts(frame, site_keyer=site_keyer)
    if material_mode != "raw":
        raise ValueError(f"unsupported scope material mode: {material_mode}")
    site_col = _find_column(
        frame,
        "site id",
        "*du id",
        "*du id 站点 id",
        "site id radio/站点",
    )
    region_col = _find_column(frame, "region", "region/区域", "区域")
    item_col = _find_column(
        frame,
        "*物料编码",
        "item code",
        "item_code",
        "*bom/编码",
    )
    new_col = _find_column(frame, "new", "installation outbound/增加数量")
    redeploy_col = _find_column(frame, "redeploy")
    dismantle_col = _find_column(frame, "dismantle", "dismantling inbound/减少数量")
    # Input4 variants such as TH carry Existing, install-outbound, and
    # dismantle-inbound quantities together.  The fuzzy ``数量`` lookup can
    # otherwise select Existing and silently reinterpret current stock as a
    # signed site action.  Explicit action columns are authoritative whenever
    # either side is present; retain signed-quantity parsing only for schemas
    # that genuinely expose no split action columns.
    signed_col = (
        None
        if new_col is not None or dismantle_col is not None
        else _find_column(frame, "*数量", "数量")
    )
    if site_col is None or item_col is None:
        raise ValueError("scope input lacks site/item fields")
    if signed_col is None and new_col is None and dismantle_col is None:
        raise ValueError("scope input lacks Prompt material quantity fields")

    scoped = frame.loc[
        frame[site_col].map(_norm).ne("") & frame[item_col].map(_norm).ne("")
    ].copy()

    def quantities(column: str | None) -> pd.Series:
        if column is None:
            return pd.Series(0, index=scoped.index, dtype="int64")
        raw = scoped[column]
        numeric = pd.to_numeric(raw, errors="coerce")
        nonempty = raw.map(_norm).ne("")
        if bool((nonempty & numeric.isna()).any()):
            raise ValueError(f"scope input contains a nonnumeric quantity in {column}")
        if bool((numeric.notna() & numeric.mod(1).ne(0)).any()):
            raise ValueError("scope input material quantities must be integers")
        return numeric.fillna(0).astype("int64")

    sites = scoped[site_col].map(_norm).map(site_keyer)
    regions = (
        scoped[region_col].map(_norm).map(_key)
        if region_col
        else pd.Series("all", index=scoped.index)
    )
    items = scoped[item_col].map(_bom_key)
    rows: list[pd.DataFrame] = []
    if signed_col is not None:
        signed = quantities(signed_col)
        for action, mask in (
            ("install", signed.gt(0)),
            ("dismantle", signed.lt(0)),
        ):
            rows.append(
                pd.DataFrame(
                    {
                        "key": regions[mask] + "|" + sites[mask] + "|" + action,
                        "item": items[mask],
                        "quantity": signed[mask],
                    }
                )
            )
    else:
        install = quantities(new_col) + quantities(redeploy_col)
        dismantle = quantities(dismantle_col)
        for action, values, mask in (
            ("install", install, install.gt(0)),
            ("dismantle", -dismantle, dismantle.gt(0)),
        ):
            rows.append(
                pd.DataFrame(
                    {
                        "key": regions[mask] + "|" + sites[mask] + "|" + action,
                        "item": items[mask],
                        "quantity": values[mask],
                    }
                )
            )
    material_rows = pd.concat(rows, ignore_index=True)
    grouped = material_rows.groupby(["key", "item"], as_index=False)["quantity"].sum()
    facts: dict[str, dict[str, int]] = defaultdict(dict)
    for key, item, quantity in grouped.itertuples(index=False, name=None):
        if int(quantity) != 0:
            facts[str(key)][str(item)] = int(quantity)
    output = {
        key: {item: quantity for item, quantity in values.items() if quantity != 0}
        for key, values in facts.items()
    }
    output = {key: values for key, values in output.items() if values}
    if not output:
        raise ValueError("scope input produced no site-action material facts")
    return output
