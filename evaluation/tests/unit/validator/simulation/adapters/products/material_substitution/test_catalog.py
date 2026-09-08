from __future__ import annotations

import pandas as pd

from simulation.ei.core.adapters.products import normalize_product
from simulation.ei.core.adapters.products.material_substitution import (
    NormalizedMaterialSubstitution,
    identity_catalog,
    normalize,
)


def _options(mode: str) -> dict[str, object]:
    return {"_effective_delivery": {"o2_substitution_mode": mode}}


def _structured(*rows: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=(
            "solution_id",
            "priority",
            "target_item_code",
            "target_qty",
            "sub_item_code",
            "sub_qty",
            "new_issue_item_code",
        ),
    )


def _row(
    solution: str,
    priority: int,
    target: str,
    target_quantity: int,
    substitute: str,
    substitute_quantity: int,
    fallback: str = "",
) -> dict[str, object]:
    return {
        "solution_id": solution,
        "priority": priority,
        "target_item_code": target,
        "target_qty": target_quantity,
        "sub_item_code": substitute,
        "sub_qty": substitute_quantity,
        "new_issue_item_code": fallback,
    }


def test_defined_target_remains_directly_fulfillable_at_one_to_one() -> None:
    source = _structured(
        _row("S_P1", 1, "A", 1, "", 0),
        _row("S_P2", 2, "", 0, "B", 1),
    )

    catalog, issues = normalize(source, _options("legacy-combination"))

    assert issues == ()
    assert isinstance(catalog, NormalizedMaterialSubstitution)
    assert catalog.target("A").defined is True
    assert catalog.target("A").allow_original is True
    assert catalog.matcher_options_for("A") == (
        (1, (("a", 1),)),
        (1, (("b", 1),)),
    )


def test_explicit_identity_is_preserved_with_its_source_provenance() -> None:
    source = _structured(
        _row("S_P1", 1, "A", 1, "A", 1),
        _row("S_P2", 2, "", 0, "B", 1),
    )

    catalog, _ = normalize(source, _options("priority-row-views"))

    target = catalog.target("A")
    assert target.allow_original is True
    assert [(value.priority, value.role, value.source_rows) for value in target.options] == [
        (1, "identity", (2,)),
        (2, "substitute", (3,)),
    ]
    assert catalog.matcher_options_for("A") == (
        (1, (("a", 1),)),
        (1, (("b", 1),)),
    )


def test_undefined_target_has_an_explicit_no_replacement_identity_policy() -> None:
    catalog, _ = normalize(
        _structured(
            _row("S_P1", 1, "A", 1, "", 0),
            _row("S_P2", 2, "", 0, "B", 1),
        ),
        _options("legacy-combination"),
    )

    target = catalog.target("C")

    assert catalog.undefined_target_policy == "identity-only"
    assert target.defined is False
    assert target.allow_original is True
    assert target.options[0].role == "no-replacement-identity"
    assert catalog.matcher_mapping(("A", "C")) == {
        "a": ((1, (("a", 1),)), (1, (("b", 1),))),
        "c": ((1, (("c", 1),)),),
    }


def test_one_priority_is_one_and_bundle_and_priorities_are_or_options() -> None:
    source = _structured(
        _row("S_P1", 1, "A", 2, "", 0),
        _row("S_P2", 2, "", 0, "B", 1),
        _row("S_P2", 2, "", 0, "C", 2),
        _row("S_P3", 3, "", 0, "D", 2),
    )

    catalog, _ = normalize(source, _options("priority-row-views"))

    assert catalog.matcher_options_for("A") == (
        (1, (("a", 1),)),
        (2, (("b", 1), ("c", 2))),
        (2, (("d", 2),)),
    )
    assert [value.priority for value in catalog.target("A").options] == [2, 3]


def _raw_input5(*rows: tuple[str, int, tuple[tuple[str, int], ...]]) -> pd.DataFrame:
    values: list[list[object]] = [
        ["header", *("" for _ in range(13))],
        ["header", *("" for _ in range(13))],
    ]
    for group, priority, bundle in rows:
        row: list[object] = [""] * 14
        row[0] = group
        row[1] = priority
        for (item, quantity), (item_column, quantity_column) in zip(
            bundle,
            ((2, 5), (6, 9), (10, 13)),
        ):
            row[item_column] = item
            row[quantity_column] = quantity
        values.append(row)
    return pd.DataFrame(values)


def test_raw_input5_preserves_compound_options_and_bidirectional_provenance() -> None:
    source = _raw_input5(
        ("G1", 1, (("A", 2),)),
        ("G1", 2, (("B", 1),)),
        ("G1", 3, (("C", 2),)),
        ("G1", 4, (("NEW_A", 2),)),
        ("G2", 1, (("X", 1),)),
        ("G2", 2, (("Y", 1), ("Z", 2))),
    )

    catalog, _ = normalize(source, _options("expanded-bidirectional"))

    assert catalog.matcher_options_for("A") == (
        (1, (("a", 1),)),
        (2, (("b", 1),)),
        (2, (("c", 2),)),
        (2, (("new_a", 2),)),
    )
    assert catalog.matcher_options_for("B") == (
        (1, (("b", 1),)),
        (1, (("c", 2),)),
        (1, (("new_a", 2),)),
    )
    assert catalog.matcher_options_for("X") == (
        (1, (("x", 1),)),
        (1, (("y", 1), ("z", 2))),
    )
    reverse = catalog.target("B").options[0]
    assert reverse.source_group == "G1"
    assert reverse.source_rows == (5,)
    assert reverse.derived_from == (4,)


def test_legacy_target_fallback_mode_makes_the_source_target_explicit() -> None:
    source = _raw_input5(
        ("G1", 1, (("NEW_A", 1),)),
        ("G1", 2, (("A_REUSE", 1),)),
    )

    catalog, _ = normalize(source, _options("legacy-target-fallback"))

    target = catalog.target("NEW_A")
    assert target.allow_original is True
    assert [(value.priority, value.role) for value in target.options] == [
        (1, "fallback"),
        (2, "substitute"),
    ]


def test_identity_only_catalog_materializes_each_authority_item() -> None:
    catalog = identity_catalog()

    assert catalog.targets == {}
    assert catalog.matcher_mapping(("A", "B")) == {
        "a": ((1, (("a", 1),)),),
        "b": ((1, (("b", 1),)),),
    }


def test_only_question_substitution_source_is_compiled_as_o2_authority() -> None:
    source = _structured(
        _row("AUTH_P1", 1, "A", 1, "", 0),
        _row("AUTH_P2", 2, "", 0, "B", 1),
    )
    candidate = _structured(
        _row("FAKE_P1", 1, "A", 1, "A", 1),
    )

    authority, _ = normalize_product(
        "substitution_source",
        "ei.material-substitution",
        source,
        _options("legacy-combination"),
    )
    candidate_product, _ = normalize_product(
        "material_substitution",
        "ei.material-substitution",
        candidate,
        _options("legacy-combination"),
    )

    assert isinstance(authority, NormalizedMaterialSubstitution)
    assert authority.target("A").allow_original is True
    assert isinstance(candidate_product, pd.DataFrame)
    assert candidate_product.loc[0, "sub_item_code"] == "A"
