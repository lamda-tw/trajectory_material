import pandas as pd

from simulation.ei.rules.ei_standard.scheduling.c5 import score_c5

from .support import context, evidence


def test_c5_scores_batch_quantity_directly() -> None:
    prepared = evidence()
    result = score_c5(
        context("C5"),
        evidence(plan=prepared.plan[prepared.plan["site_key"] == "r|s1"]),
    )
    assert result.check_id == "scheduling.C5"
    assert result.score == 50.0


def test_c5_region_pool_rounds_install_sites_once_across_batches() -> None:
    site_keys = [f"r|s{index}" for index in range(1, 11)]
    expected = pd.DataFrame(
        {
            "site_key": site_keys,
            "action_key": [f"{site}|install" for site in site_keys],
            "action": ["install"] * 10,
        }
    )
    plan = pd.DataFrame(
        {
            "site_key": site_keys[:9],
            "action": ["install"] * 9,
            "week_issue": [""] * 9,
            "project_week": [1] * 9,
        }
    )
    batch_map = {
        site: "C1" if index <= 5 else "C2"
        for index, site in enumerate(site_keys, start=1)
    }
    common = {
        "plan": plan,
        "expected": expected,
        "expected_sites": set(site_keys),
        "actual_sites": set(site_keys[:9]),
        "batch_map": batch_map,
    }
    batch_parameters = {
        "batch_kind": "cluster",
        "skip_rate": 0.1,
        "skip_pool_scope": "region-batch",
    }
    region_parameters = {
        **batch_parameters,
        "skip_pool_scope": "region",
    }

    batch_result = score_c5(
        context("C5", parameters=batch_parameters),
        evidence(**common, parameters=batch_parameters),
    )
    region_result = score_c5(
        context("C5", parameters=region_parameters),
        evidence(**common, parameters=region_parameters),
    )

    assert batch_result.evidence["expected"] == 10
    assert batch_result.score == 90.0
    assert region_result.evidence["expected"] == 9
    assert region_result.evidence["skip_pool_scope"] == "region"
    assert region_result.score == 100.0


def test_c5_replays_fixed_seed_drop_identity_in_batch_source_order() -> None:
    first_batch = [f"r1|s{index}" for index in range(20, 0, -1)]
    second_batch = [f"r2|t{index}" for index in range(1, 21)]
    site_keys = first_batch + second_batch
    expected = pd.DataFrame(
        {
            "site_key": site_keys,
            "action_key": [f"{site}|install" for site in site_keys],
            "action": ["install"] * len(site_keys),
        }
    )
    # Python Random(42) selects source-position 3 from the first sorted batch
    # and position 0 from the second when one global RNG is reused.
    expected_dropped = {"r1|s17", "r2|t1"}
    retained = [site for site in site_keys if site not in expected_dropped]

    def valid_plan(sites: list[str]) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "site_key": sites,
                "action": ["install"] * len(sites),
                "week_issue": [""] * len(sites),
                "project_week": [1] * len(sites),
            }
        )

    parameters = {
        "batch_kind": "mocn",
        "skip_rate": 0.05,
        "skip_pool_scope": "batch",
        "drop_selection_contract": {"mode": "seeded-random", "seed": 42},
    }
    common = {
        "parameters": parameters,
        "expected": expected,
        "expected_sites": set(site_keys),
        "batch_map": {
            **{site: "1" for site in first_batch},
            **{site: "2" for site in second_batch},
        },
    }

    exact = score_c5(
        context("C5", parameters=parameters),
        evidence(**common, plan=valid_plan(retained)),
    )
    wrong_sites = [site for site in retained if site != "r1|s18"] + ["r1|s17"]
    wrong = score_c5(
        context("C5", parameters=parameters),
        evidence(**common, plan=valid_plan(wrong_sites)),
    )

    assert exact.score == 100.0
    assert set(exact.evidence["drop_selection"]["dropped_site_keys"]) == (
        expected_dropped
    )
    assert exact.evidence["drop_selection"]["authority_order"] == (
        "batch-input-source-row"
    )
    assert exact.evidence["drop_selection"]["pool_rng_scope"] == (
        "single-sequential-rng"
    )
    assert wrong.reason_code == "DROP_IDENTITY_MISMATCH"
    assert wrong.evidence["missing_retained_site_keys"] == ["r1|s18"]
    assert wrong.evidence["forbidden_dropped_site_keys"] == ["r1|s17"]
