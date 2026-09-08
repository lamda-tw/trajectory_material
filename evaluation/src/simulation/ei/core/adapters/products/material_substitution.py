"""Canonical, authoritative material-substitution product.

The physical source has two supported shapes:

* the seven-column expanded ``material_substitution.csv`` contract; and
* the headerless ``PCP0101`` worksheet from the original Input5 workbook.

The adapter compiles both shapes into the same target -> OR-options model.
Rows at one priority form one AND bundle.  Every target also remains directly
fulfillable by the same material at a case-insensitive 1:1 ratio.  The source
options stay unchanged so relation-fidelity rules can still audit only the
substitution rows that the question actually supplied.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from types import MappingProxyType
import re
from typing import Any, Iterable, Mapping

import pandas as pd

from .._shared import _material_key, _norm
from ._canonical import TabularSource, column, effective_delivery_options


_SUPPORTED_MODES = {
    "identity-only",
    "legacy-combination",
    "legacy-target-fallback",
    "expanded-bidirectional",
    "priority-row-views",
}


@dataclass(frozen=True)
class SubstitutionOption:
    """One legal OR option; every material in ``bundle`` is required (AND)."""

    target_quantity: int
    bundle: tuple[tuple[str, int], ...]
    priority: int
    role: str
    solution_id: str = ""
    source_group: str = ""
    source_sheet: str = ""
    source_rows: tuple[int, ...] = ()
    derived_from: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.target_quantity <= 0:
            raise ValueError("substitution target quantity must be positive")
        if self.priority <= 0:
            raise ValueError("substitution priority must be positive")
        if not self.bundle or any(not item or quantity <= 0 for item, quantity in self.bundle):
            raise ValueError("substitution bundle must contain positive material quantities")


@dataclass(frozen=True)
class TargetSubstitution:
    """All legal options for one source-defined target material."""

    target_item_code: str
    defined: bool
    allow_original: bool
    options: tuple[SubstitutionOption, ...]
    source_groups: tuple[str, ...] = ()
    source_rows: tuple[int, ...] = ()


@dataclass(frozen=True)
class NormalizedMaterialSubstitution:
    """Immutable catalog consumed by business rules.

    ``undefined_target_policy`` is deliberately explicit.  A material absent
    from the relation table is not a replaceable target, so its only legal
    delivery is itself.  A material present in ``targets`` may use its source-
    defined replacement options or the original material itself at 1:1.
    """

    mode: str
    source_kind: str
    targets: Mapping[str, TargetSubstitution]
    undefined_target_policy: str = "identity-only"
    source_sheet: str = ""
    _target_index: Mapping[str, TargetSubstitution] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if self.mode not in _SUPPORTED_MODES:
            raise ValueError(f"unsupported substitution mode: {self.mode}")
        if self.undefined_target_policy != "identity-only":
            raise ValueError("unsupported undefined-target policy")
        index = {
            _material_key(key): value
            for key, value in self.targets.items()
        }
        object.__setattr__(self, "targets", MappingProxyType(dict(sorted(index.items()))))
        object.__setattr__(self, "_target_index", self.targets)

    @property
    def defined_target_codes(self) -> tuple[str, ...]:
        return tuple(self._target_index)

    def target(self, item_code: Any) -> TargetSubstitution:
        """Return a source target or an explicit no-replacement identity view."""

        item = _material_key(item_code)
        defined = self._target_index.get(item)
        if defined is not None:
            return defined
        if not item:
            raise ValueError("material item code is blank")
        option = SubstitutionOption(
            target_quantity=1,
            bundle=((item, 1),),
            priority=1,
            role="no-replacement-identity",
        )
        return TargetSubstitution(
            target_item_code=item,
            defined=False,
            allow_original=True,
            options=(option,),
        )

    def matcher_options_for(
        self,
        item_code: Any,
    ) -> tuple[tuple[int, tuple[tuple[str, int], ...]], ...]:
        """Project the rich catalog onto the strict material matcher's shape."""

        target = self.target(item_code)
        identity = (1, ((target.target_item_code, 1),))
        return tuple(
            sorted(
                {
                    (option.target_quantity, option.bundle)
                    for option in target.options
                } | {identity}
            )
        )

    def matcher_mapping(
        self,
        item_codes: Iterable[Any],
    ) -> dict[str, tuple[tuple[int, tuple[tuple[str, int], ...]], ...]]:
        """Materialize every authority item, including undefined identities."""

        items = {_material_key(value) for value in item_codes}
        return {
            item: self.matcher_options_for(item)
            for item in sorted(value for value in items if value)
        }


def identity_catalog() -> NormalizedMaterialSubstitution:
    """Return the explicit no-replacement catalog used by identity-only O2."""

    return NormalizedMaterialSubstitution(
        mode="identity-only",
        source_kind="identity-only",
        targets={},
    )


def _positive_integer(value: Any, *, field_name: str) -> int:
    text = _norm(value)
    try:
        parsed = float(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive integer") from exc
    if not pd.notna(parsed) or not parsed.is_integer() or int(parsed) <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return int(parsed)


def _bundle(values: Iterable[tuple[str, int]]) -> tuple[tuple[str, int], ...]:
    quantities: dict[str, int] = defaultdict(int)
    for item, quantity in values:
        normalized = _material_key(item)
        if normalized:
            quantities[normalized] += int(quantity)
    return tuple(sorted((item, quantity) for item, quantity in quantities.items() if quantity > 0))


def _target_catalog(
    mode: str,
    source_kind: str,
    source_sheet: str,
    options: Mapping[str, list[SubstitutionOption]],
) -> NormalizedMaterialSubstitution:
    targets: dict[str, TargetSubstitution] = {}
    for target, raw_options in sorted(options.items()):
        ordered = tuple(
            sorted(
                raw_options,
                key=lambda value: (
                    value.priority,
                    value.bundle,
                    value.role,
                    value.solution_id,
                    value.source_rows,
                ),
            )
        )
        if not ordered:
            raise ValueError(f"defined substitution target has no legal options: {target}")
        targets[target] = TargetSubstitution(
            target_item_code=target,
            defined=True,
            allow_original=True,
            options=ordered,
            source_groups=tuple(
                sorted({value.source_group for value in ordered if value.source_group})
            ),
            source_rows=tuple(sorted({row for value in ordered for row in value.source_rows})),
        )
    if mode != "identity-only" and not targets:
        raise ValueError("substitution source produced no legal target options")
    return NormalizedMaterialSubstitution(
        mode=mode,
        source_kind=source_kind,
        targets=targets,
        source_sheet=source_sheet,
    )


def _structured_columns(frame: pd.DataFrame) -> dict[str, str] | None:
    aliases = {
        "solution": ("solution_id", "solution id"),
        "priority": ("priority",),
        "target": ("target_item_code", "target item code"),
        "target_quantity": ("target_qty", "target quantity"),
        "substitute": ("sub_item_code", "substitute_item_code", "sub item code"),
        "substitute_quantity": ("sub_qty", "substitute_quantity", "sub quantity"),
        "fallback": ("new_issue_item_code", "new issue item code"),
    }
    resolved = {
        name: column(frame, values)
        for name, values in aliases.items()
    }
    required = {
        "solution",
        "priority",
        "target",
        "target_quantity",
        "substitute",
        "substitute_quantity",
    }
    return resolved if all(resolved[name] is not None for name in required) else None


def _structured_catalog(
    frame: pd.DataFrame,
    *,
    mode: str,
    source_sheet: str,
) -> NormalizedMaterialSubstitution:
    columns = _structured_columns(frame)
    if columns is None:
        raise ValueError("structured substitution source lacks canonical columns")

    views: dict[str, dict[str, Any]] = {}
    current_by_solution: dict[str, tuple[str, int]] = {}
    for position, (_, row) in enumerate(frame.iterrows(), start=2):
        solution_raw = _norm(row.get(columns["solution"]))
        target_raw = _material_key(row.get(columns["target"]))
        substitute = _material_key(row.get(columns["substitute"]))
        fallback = (
            _material_key(row.get(columns["fallback"]))
            if columns.get("fallback") is not None
            else ""
        )
        priority_raw = _norm(row.get(columns["priority"]))
        if not any((solution_raw, target_raw, substitute, fallback, priority_raw)):
            continue
        priority = _positive_integer(priority_raw, field_name="priority")
        solution = re.sub(r"_p\d+(?:_\d+)?$", "", solution_raw.casefold())
        if not solution:
            raise ValueError(f"solution_id is required at source row {position}")
        if target_raw:
            target_quantity = _positive_integer(
                row.get(columns["target_quantity"]),
                field_name="target_qty",
            )
            prior = current_by_solution.get(solution)
            if prior is not None and prior != (target_raw, target_quantity):
                raise ValueError(f"target conflicts within solution {solution!r}")
            current_by_solution[solution] = (target_raw, target_quantity)
        target_fact = current_by_solution.get(solution)
        if target_fact is None:
            raise ValueError(
                "substitution row cannot be linked to a target "
                f"at source row {position}"
            )
        target, target_quantity = target_fact
        view = views.setdefault(
            solution,
            {
                "target": target,
                "target_quantity": target_quantity,
                "levels": defaultdict(list),
                "rows": defaultdict(list),
                "fallbacks": defaultdict(list),
            },
        )
        if (view["target"], view["target_quantity"]) != target_fact:
            raise ValueError(f"target conflicts within solution {solution!r}")
        if substitute:
            quantity = _positive_integer(
                row.get(columns["substitute_quantity"]),
                field_name="sub_qty",
            )
            view["levels"][priority].append((substitute, quantity))
            view["rows"][priority].append(position)
        elif _norm(row.get(columns["substitute_quantity"])) not in {"", "0", "0.0"}:
            raise ValueError(f"sub_qty exists without sub_item_code at source row {position}")
        if fallback:
            view["fallbacks"][fallback].append(position)

    by_target: dict[str, list[SubstitutionOption]] = defaultdict(list)
    for solution, view in sorted(views.items()):
        target = str(view["target"])
        target_quantity = int(view["target_quantity"])
        explicit_bundles: set[tuple[tuple[str, int], ...]] = set()
        for priority, values in sorted(view["levels"].items()):
            bundle = _bundle(values)
            if not bundle:
                continue
            explicit_bundles.add(bundle)
            fallback_codes = set(view["fallbacks"])
            role = (
                "identity"
                if bundle == ((target, target_quantity),)
                else "fallback"
                if len(bundle) == 1 and bundle[0][0] in fallback_codes
                else "substitute"
            )
            by_target[target].append(
                SubstitutionOption(
                    target_quantity=target_quantity,
                    bundle=bundle,
                    priority=int(priority),
                    role=role,
                    solution_id=solution,
                    source_group=solution,
                    source_sheet=source_sheet,
                    source_rows=tuple(sorted(set(view["rows"][priority]))),
                )
            )
        next_priority = max(view["levels"], default=0) + 1
        for fallback, rows in sorted(view["fallbacks"].items()):
            fallback_bundle = ((fallback, target_quantity),)
            if fallback_bundle in explicit_bundles:
                continue
            by_target[target].append(
                SubstitutionOption(
                    target_quantity=target_quantity,
                    bundle=fallback_bundle,
                    priority=next_priority,
                    role="fallback",
                    solution_id=solution,
                    source_group=solution,
                    source_sheet=source_sheet,
                    source_rows=tuple(sorted(set(rows))),
                )
            )
            next_priority += 1

    return _target_catalog(mode, "structured", source_sheet, by_target)


def _pcp0101_frame(source: TabularSource) -> tuple[pd.DataFrame, str]:
    if isinstance(source, pd.DataFrame):
        return source, str(source.attrs.get("source_sheet", "PCP0101"))
    exact = [
        (str(name), frame)
        for name, frame in source.items()
        if isinstance(frame, pd.DataFrame) and _norm(name).casefold() == "pcp0101"
    ]
    if len(exact) != 1:
        raise ValueError("resolved substitution workbook must contain exactly one PCP0101 sheet")
    return exact[0][1], exact[0][0]


def _raw_levels(
    frame: pd.DataFrame,
) -> dict[str, dict[int, tuple[tuple[tuple[str, int], ...], tuple[int, ...]]]]:
    groups: dict[str, dict[int, list[tuple[tuple[str, int], ...] | int]]] = defaultdict(dict)
    for physical_position, (_, row) in enumerate(frame.iterrows(), start=1):
        # Input5 has two physical header rows.  Header text and spacer rows are
        # naturally ignored because priority is not a positive integer.
        group = _norm(row.iloc[0] if len(row) else "")
        priority_raw = _norm(row.iloc[1] if len(row) > 1 else "")
        if not group or not priority_raw:
            continue
        try:
            priority = _positive_integer(priority_raw, field_name="priority")
        except ValueError:
            continue
        materials: list[tuple[str, int]] = []
        for item_index, quantity_index in ((2, 5), (6, 9), (10, 13)):
            item = _material_key(row.iloc[item_index] if len(row) > item_index else "")
            quantity_raw = row.iloc[quantity_index] if len(row) > quantity_index else ""
            if not item:
                if _norm(quantity_raw):
                    raise ValueError(
                        f"Input5 quantity exists without item at source row {physical_position}"
                    )
                continue
            materials.append(
                (item, _positive_integer(quantity_raw, field_name="Input5 material quantity"))
            )
        bundle = _bundle(materials)
        if not bundle:
            continue
        prior = groups[group].get(priority)
        if prior is not None:
            raise ValueError(f"duplicate priority {priority} in Input5 group {group!r}")
        groups[group][priority] = [bundle, physical_position]
    return {
        group: {
            priority: (value[0], (int(value[1]),))  # type: ignore[arg-type]
            for priority, value in sorted(levels.items())
        }
        for group, levels in sorted(groups.items())
        if levels
    }


def _raw_catalog(
    frame: pd.DataFrame,
    *,
    mode: str,
    source_sheet: str,
) -> NormalizedMaterialSubstitution:
    groups = _raw_levels(frame)
    by_target: dict[str, list[SubstitutionOption]] = defaultdict(list)
    for group, levels in groups.items():
        ordered = [
            (priority, bundle, rows)
            for priority, (bundle, rows) in sorted(levels.items())
        ]
        if len(ordered) < 2:
            continue
        first_priority, first_bundle, first_rows = ordered[0]
        if len(first_bundle) != 1:
            raise ValueError(f"Input5 target row must contain one material in group {group!r}")
        target, target_quantity = first_bundle[0]

        if mode == "legacy-target-fallback":
            by_target[target].append(
                SubstitutionOption(
                    target_quantity=target_quantity,
                    bundle=((target, target_quantity),),
                    priority=first_priority,
                    role="fallback",
                    solution_id=group.casefold(),
                    source_group=group,
                    source_sheet=source_sheet,
                    source_rows=first_rows,
                )
            )

        for priority, bundle, rows in ordered[1:]:
            by_target[target].append(
                SubstitutionOption(
                    target_quantity=target_quantity,
                    bundle=bundle,
                    priority=priority,
                    role=(
                        "identity"
                        if bundle == ((target, target_quantity),)
                        else "fallback"
                        if len(bundle) == 1 and bundle[0][0].startswith("new_")
                        else "substitute"
                    ),
                    solution_id=group.casefold(),
                    source_group=group,
                    source_sheet=source_sheet,
                    source_rows=rows,
                )
            )

        if mode != "expanded-bidirectional":
            continue
        last_bundle = ordered[-1][1]
        last_is_fallback = len(last_bundle) == 1 and last_bundle[0][0].startswith("new_")
        intermediate = ordered[1:-1] if last_is_fallback else ordered[1:]
        fallback = ordered[-1] if last_is_fallback else None
        for target_index, (target_priority, target_bundle, target_rows) in enumerate(intermediate):
            if len(target_bundle) != 1:
                # A compound option has no single material identity and cannot
                # become a reverse target.  It remains a legal option for the
                # primary target above.
                continue
            reverse_target, reverse_quantity = target_bundle[0]
            for option_index, (priority, bundle, rows) in enumerate(intermediate):
                if option_index == target_index:
                    continue
                by_target[reverse_target].append(
                    SubstitutionOption(
                        target_quantity=reverse_quantity,
                        bundle=bundle,
                        priority=priority,
                        role=(
                            "identity"
                            if bundle == ((reverse_target, reverse_quantity),)
                            else "substitute"
                        ),
                        solution_id=f"{group.casefold()}:{target_priority}",
                        source_group=group,
                        source_sheet=source_sheet,
                        source_rows=rows,
                        derived_from=target_rows,
                    )
                )
            if fallback is not None:
                priority, bundle, rows = fallback
                by_target[reverse_target].append(
                    SubstitutionOption(
                        target_quantity=reverse_quantity,
                        bundle=bundle,
                        priority=priority,
                        role="fallback",
                        solution_id=f"{group.casefold()}:{target_priority}",
                        source_group=group,
                        source_sheet=source_sheet,
                        source_rows=rows,
                        derived_from=target_rows,
                    )
                )

    return _target_catalog(mode, "pcp0101", source_sheet, by_target)


def normalize(
    frame: TabularSource,
    options: Mapping[str, Any],
) -> tuple[NormalizedMaterialSubstitution, tuple[dict[str, Any], ...]]:
    """Compile the selected authoritative table without any candidate lookup."""

    parameters = effective_delivery_options(options)
    mode = _norm(
        parameters.get("o2_substitution_mode")
        or options.get("o2_substitution_mode")
        or options.get("substitution_mode")
    ).casefold()
    if not mode:
        # The seven-column product has one unambiguous interpretation.  Raw
        # Input5 needs a question-level mode because its target expansion is
        # intentionally different between legacy and bidirectional prompts.
        if isinstance(frame, pd.DataFrame) and _structured_columns(frame) is not None:
            mode = "priority-row-views"
        else:
            raise ValueError("substitution normalization requires o2_substitution_mode")
    if mode not in _SUPPORTED_MODES:
        raise ValueError(f"unsupported substitution mode: {mode}")
    if mode == "identity-only":
        return identity_catalog(), ()

    if isinstance(frame, pd.DataFrame) and _structured_columns(frame) is not None:
        sheet = str(frame.attrs.get("source_sheet", ""))
        return _structured_catalog(frame, mode=mode, source_sheet=sheet), ()
    raw, sheet = _pcp0101_frame(frame)
    if _structured_columns(raw) is not None:
        return _structured_catalog(raw, mode=mode, source_sheet=sheet), ()
    return _raw_catalog(raw, mode=mode, source_sheet=sheet), ()


__all__ = [
    "NormalizedMaterialSubstitution",
    "SubstitutionOption",
    "TargetSubstitution",
    "identity_catalog",
    "normalize",
]
