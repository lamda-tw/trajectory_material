"""Strict configuration loader for EI's five aggregate metrics."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable


KEY_CHECK_IDS = (
    "scheduling.C2",
    "scheduling.C6a",
    "scheduling-pacing.O1",
    "simulation.S1",
    "simulation.S5",
)
O2_CHECK_ID = "effective-delivery.O2"


class AggregationConfigurationError(ValueError):
    """Raised when an aggregation policy is incomplete or ambiguous."""


@dataclass(frozen=True)
class ScoreBand:
    max_deduction: Decimal
    score: Decimal


@dataclass(frozen=True)
class AggregationRule:
    check_id: str
    weight: int
    ladder: tuple[ScoreBand, ...] = ()


@dataclass(frozen=True)
class AggregationPolicy:
    ruleset_release: str
    policy_id: str
    rules: tuple[AggregationRule, ...]
    effectiveness_check_id: str = O2_CHECK_ID
    all_rules: tuple[AggregationRule, ...] = ()

    @property
    def contract(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "ruleset_release": self.ruleset_release,
            "metric_order": [
                "effectiveness.o2",
                "key.raw",
                "key.discrete",
                "key.piecewise",
                "all.raw",
            ],
        }


def _decimal(value: Any, *, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise AggregationConfigurationError(f"{label} must be numeric")
    try:
        result = Decimal(str(value))
    except Exception as exc:  # noqa: BLE001
        raise AggregationConfigurationError(f"{label} must be numeric") from exc
    if not result.is_finite():
        raise AggregationConfigurationError(f"{label} must be finite")
    return result


def _load_rule(
    check_id: str,
    raw: Any,
    *,
    require_ladder: bool,
) -> AggregationRule:
    if not isinstance(check_id, str) or not check_id or "." not in check_id:
        raise AggregationConfigurationError(
            f"aggregation rule ID must be a full check ID: {check_id!r}"
        )
    if not isinstance(raw, dict):
        raise AggregationConfigurationError(f"aggregation rule {check_id} must be a mapping")
    expected = {"weight", "ladder"} if require_ladder else {"weight"}
    if set(raw) != expected:
        raise AggregationConfigurationError(
            f"aggregation rule {check_id} requires only {sorted(expected)}"
        )
    weight = raw.get("weight")
    if not isinstance(weight, int) or isinstance(weight, bool) or not 1 <= weight <= 100:
        raise AggregationConfigurationError(
            f"aggregation rule {check_id} weight must be an integer in [1, 100]"
        )
    if not require_ladder:
        return AggregationRule(check_id, weight)
    raw_ladder = raw.get("ladder")
    if not isinstance(raw_ladder, list) or not raw_ladder:
        raise AggregationConfigurationError(
            f"aggregation rule {check_id} ladder must be a non-empty list"
        )
    ladder: list[ScoreBand] = []
    previous = Decimal("-1")
    previous_score = Decimal("101")
    for index, raw_band in enumerate(raw_ladder):
        if not isinstance(raw_band, dict) or set(raw_band) != {"max_deduction", "score"}:
            raise AggregationConfigurationError(
                f"aggregation rule {check_id} ladder[{index}] requires only "
                "max_deduction and score"
            )
        boundary = _decimal(
            raw_band["max_deduction"],
            label=f"{check_id}.ladder[{index}].max_deduction",
        )
        converted = _decimal(
            raw_band["score"], label=f"{check_id}.ladder[{index}].score"
        )
        if not Decimal("0") <= boundary <= Decimal("100"):
            raise AggregationConfigurationError(
                f"{check_id} ladder boundary must be in [0, 100]"
            )
        if boundary <= previous:
            raise AggregationConfigurationError(
                f"{check_id} ladder boundaries must be strictly increasing"
            )
        if not Decimal("0") <= converted <= Decimal("100"):
            raise AggregationConfigurationError(
                f"{check_id} ladder score must be in [0, 100]"
            )
        if converted > previous_score:
            raise AggregationConfigurationError(
                f"{check_id} ladder score must not increase as deduction grows"
            )
        ladder.append(ScoreBand(boundary, converted))
        previous = boundary
        previous_score = converted
    if ladder[-1].max_deduction != Decimal("100"):
        raise AggregationConfigurationError(
            f"aggregation rule {check_id} ladder must end at deduction 100"
        )
    return AggregationRule(check_id, weight, tuple(ladder))


def _mapping(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise AggregationConfigurationError(f"{label} must be a non-empty mapping")
    return value


def load_aggregation_policy(
    ruleset: dict[str, Any] | None = None,
    *,
    allowed_check_ids: Iterable[str] | None = None,
) -> AggregationPolicy:
    """Compile the aggregation policy frozen inside one immutable ruleset release."""

    if ruleset is None:
        from simulation.ei.core.config import load_ruleset

        ruleset = load_ruleset()
    if not isinstance(ruleset, dict):
        raise AggregationConfigurationError("ruleset must be a mapping")
    release = ruleset.get("release")
    payload = ruleset.get("aggregation")
    if not isinstance(release, str) or not release:
        raise AggregationConfigurationError("ruleset release must be a non-empty string")
    if not isinstance(payload, dict):
        raise AggregationConfigurationError("ruleset aggregation must be a mapping")
    allowed_top = {"policy_id", "effectiveness", "key", "all"}
    unexpected = set(payload) - allowed_top
    if unexpected:
        raise AggregationConfigurationError(
            f"unknown aggregation configuration keys: {sorted(unexpected)}"
        )
    policy_id = payload.get("policy_id")
    if not isinstance(policy_id, str) or not policy_id.strip():
        raise AggregationConfigurationError("policy_id must be a non-empty string")

    allowed = set(allowed_check_ids) if allowed_check_ids is not None else None
    effectiveness = _mapping(payload.get("effectiveness"), label="effectiveness")
    if set(effectiveness) != {"metric_id", "check_id"}:
        raise AggregationConfigurationError(
            "effectiveness requires only metric_id and check_id"
        )
    if effectiveness.get("metric_id") != "effectiveness.o2":
        raise AggregationConfigurationError(
            "effectiveness.metric_id must be effectiveness.o2"
        )
    effectiveness_check_id = effectiveness.get("check_id")
    if effectiveness_check_id != O2_CHECK_ID:
        raise AggregationConfigurationError(
            f"effectiveness.check_id must be {O2_CHECK_ID}"
        )

    key = _mapping(payload.get("key"), label="key")
    if set(key) != {"unsupported_rule", "rules"}:
        raise AggregationConfigurationError(
            "key requires only unsupported_rule and rules"
        )
    if key.get("unsupported_rule") != "full_credit":
        raise AggregationConfigurationError("key.unsupported_rule must be full_credit")
    raw_key_rules = _mapping(key.get("rules"), label="key.rules")
    if tuple(raw_key_rules) != KEY_CHECK_IDS:
        raise AggregationConfigurationError(
            f"key.rules must be ordered exactly as {list(KEY_CHECK_IDS)}"
        )
    rules = tuple(
        _load_rule(str(check_id), raw, require_ladder=True)
        for check_id, raw in raw_key_rules.items()
    )

    all_group = _mapping(payload.get("all"), label="all")
    if set(all_group) != {"metric_id", "unsupported_rule", "rules"}:
        raise AggregationConfigurationError(
            "all requires only metric_id, unsupported_rule and rules"
        )
    if all_group.get("metric_id") != "all.raw":
        raise AggregationConfigurationError("all.metric_id must be all.raw")
    if all_group.get("unsupported_rule") != "excluded":
        raise AggregationConfigurationError("all.unsupported_rule must be excluded")
    raw_all_rules = _mapping(all_group.get("rules"), label="all.rules")
    all_rules = tuple(
        _load_rule(str(check_id), raw, require_ladder=False)
        for check_id, raw in raw_all_rules.items()
    )

    configured = {effectiveness_check_id, *(rule.check_id for rule in all_rules)}
    if len(configured) != 1 + len(all_rules):
        raise AggregationConfigurationError("O2 must not be present in all.rules")
    if allowed is not None:
        if configured != allowed:
            raise AggregationConfigurationError(
                "effectiveness plus all.rules must cover the active ruleset exactly; "
                f"missing={sorted(allowed - configured)}, extra={sorted(configured - allowed)}"
            )
    return AggregationPolicy(
        release,
        policy_id,
        rules,
        str(effectiveness_check_id),
        all_rules,
    )
