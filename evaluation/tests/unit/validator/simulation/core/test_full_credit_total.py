from simulation.ei.core.aggregation import aggregate_total, load_aggregation_policy
from simulation.ei.core.config import load_profile, load_ruleset
from simulation.ei.core.models import CheckResult, ComponentResult


def _check(check_id: str) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        name=check_id,
        score=100.0,
        status="PASS",
        reason_code="",
        explanation="test",
    )


def test_easy_question_infers_unsupported_selected_rules_from_validator_yaml() -> None:
    profile = load_profile("EI-56TESTPK0006-easy-v1.2")
    checks = (_check("simulation.S1"), _check("simulation.S5"))
    component = ComponentResult(
        question_id=profile.question_id,
        component="simulation",
        checks=checks,
        status="SCORED",
    )
    policy = load_aggregation_policy(allowed_check_ids=load_ruleset()["checks"])

    total, status, error = aggregate_total(profile, (component,), policy)

    assert total == 90.0
    assert status == "SCORED"
    assert error == ""
    assert {
        rule.check_id for rule in policy.rules if rule.check_id not in {
            check.check_id for check in checks
        }
    } == {"scheduling.C2", "scheduling.C6a", "scheduling-pacing.O1"}
