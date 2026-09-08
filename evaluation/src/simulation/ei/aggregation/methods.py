"""Pure leaf-level transforms used by EI aggregation."""

from __future__ import annotations

from decimal import Decimal

from .config import AggregationRule


def discrete_score(rule: AggregationRule, raw_score: float) -> Decimal:
    """Map a raw score through the configured deduction ladder."""

    deduction = Decimal("100") - Decimal(str(raw_score))
    for band in rule.ladder:
        if deduction <= band.max_deduction:
            return band.score
    raise AssertionError("validated aggregation ladder did not cover deduction 100")


def piecewise_score(raw_score: float) -> Decimal:
    """Amplify losses in 60..100 while compressing already-unusable results.

    The transform is continuous, monotone, and keeps a 0..100 range:
    x/3 below 60, and 2x-100 from 60 through 100.
    """

    value = Decimal(str(raw_score))
    if not Decimal("0") <= value <= Decimal("100"):
        raise ValueError(f"raw score is outside 0..100: {raw_score}")
    if value < Decimal("60"):
        return value / Decimal("3")
    return Decimal("2") * value - Decimal("100")
