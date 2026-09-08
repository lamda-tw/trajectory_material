from __future__ import annotations

from evaluation.tests.helpers.simulation_adapter_factory import load_corpus


def test_corpus_snapshot_accounts_for_every_observed_standard_artifact() -> None:
    corpus = load_corpus()

    assert corpus["snapshot"]["run_directories"] == 283
    assert corpus["snapshot"]["standard_artifact_files"] == 2174
    assert corpus["snapshot"]["alternate_serializations"] == {
        "xlsx_non_site_plan": 66,
        "json": 7,
    }
    assert sum(
        product["observed_files"] for product in corpus["products"].values()
    ) == corpus["snapshot"]["standard_artifact_files"]


def test_each_observed_family_has_a_traceable_source_and_executable_case() -> None:
    corpus = load_corpus()

    for product_name, product in corpus["products"].items():
        cases = {case["id"] for case in product["cases"]}
        assert sum(family["files"] for family in product["families"]) == product["observed_files"], product_name
        for family in product["families"]:
            assert family["case"] in cases, (product_name, family["id"])
            assert family["source"].startswith("eval_results/"), family


def test_small_table_products_account_for_every_header_signature() -> None:
    corpus = load_corpus()

    for product_name in (
        "site_plan",
        "site_material_timeline",
        "final_material",
        "material_substitution",
        "recovered_supply",
        "reuse_by_region",
        "gap",
    ):
        product = corpus["products"][product_name]
        assert sum(family["signatures"] for family in product["families"]) == product["header_signatures"], product_name


def test_every_declared_value_dialect_is_covered_by_a_case() -> None:
    corpus = load_corpus()

    for product_name, product in corpus["products"].items():
        covered = {
            tag
            for case in product["cases"]
            for tag in case.get("covers", ())
        }
        assert set(product["value_dialects"]).issubset(covered), product_name
