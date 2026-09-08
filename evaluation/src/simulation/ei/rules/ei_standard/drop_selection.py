"""Trusted deterministic Drop selection shared by C5 and O2.

The fixed scheduling engine consumes the authoritative batch-input row order,
walks deterministic pools with one process-wide seeded RNG, and samples
``floor(pool_size * drop_rate)`` install sites from every pool.  Keeping that
logic here prevents the scheduling count rule and the effective-delivery rule
from compiling different Drop identities from the same question contract.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from typing import Any, Mapping

import pandas as pd

from .batching import resolve_batch


_MODE = "seeded-random"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split())


def _site_parts(site_key: str) -> tuple[str, str]:
    region, separator, site = str(site_key).partition("|")
    if not separator or not region or not site:
        raise ValueError(f"invalid Drop site key: {site_key!r}")
    return region, site


def _batch_identity(value: Any, *, batch_kind: str) -> str:
    text = _text(value)
    if not text:
        raise ValueError("Drop batch identity is blank")
    if batch_kind == "mocn":
        try:
            number = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError(
                f"Drop MOCN batch must be a positive integer: {text!r}"
            ) from exc
        if number != number.to_integral_value() or number <= 0:
            raise ValueError(
                f"Drop MOCN batch must be a positive integer: {text!r}"
            )
        return str(int(number))
    if batch_kind == "cluster":
        return text.casefold()
    raise ValueError(f"unsupported Drop batch kind: {batch_kind!r}")


def _natural_identity(value: str) -> tuple[int, Decimal | str]:
    try:
        return (0, Decimal(value))
    except InvalidOperation:
        return (1, value.casefold())


def _validate_contract(contract: Mapping[str, Any]) -> int:
    if set(contract) != {"mode", "seed"}:
        raise ValueError(
            "Drop selection contract must contain exactly mode and seed"
        )
    if contract.get("mode") != _MODE:
        raise ValueError(f"unsupported Drop selection mode: {contract.get('mode')!r}")
    seed = contract.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("Drop selection seed must be an integer")
    return seed


@dataclass(frozen=True)
class SeededDropSelection:
    """One compiled, candidate-independent Drop authority."""

    seed: int
    rate: float
    pool_scope: str
    full_install_site_keys: frozenset[str]
    retained_install_site_keys: frozenset[str]
    dropped_install_site_keys: frozenset[str]
    pools: tuple[dict[str, Any], ...]

    def evidence(self) -> dict[str, Any]:
        return {
            "mode": _MODE,
            "algorithm": "python-random-sample-v1",
            "authority_order": "batch-input-source-row",
            "pool_rng_scope": "single-sequential-rng",
            "drop_count_formula": "floor(pool_size * drop_rate)",
            "seed": self.seed,
            "drop_rate": self.rate,
            "pool_scope": self.pool_scope,
            "full_install_sites": len(self.full_install_site_keys),
            "retained_install_sites": len(self.retained_install_site_keys),
            "dropped_install_sites": len(self.dropped_install_site_keys),
            "dropped_site_keys": sorted(self.dropped_install_site_keys),
            "retained_site_keys": sorted(self.retained_install_site_keys),
            "pools": [dict(value) for value in self.pools],
        }


def compile_seeded_drop_selection(
    expected: pd.DataFrame,
    batch_map: Mapping[str, str],
    *,
    batch_kind: str,
    drop_rate: float,
    pool_scope: str,
    contract: Mapping[str, Any],
) -> SeededDropSelection:
    """Replay the Prompt-authorized fixed-engine Drop identities.

    ``expected`` is the authoritative site/action intersection before Drop.
    Its identity is independent of candidate output.  The batch mapping's
    insertion order is the normalized source-row order and therefore freezes
    the input list passed to ``random.Random.sample``.
    """

    seed = _validate_contract(contract)
    if pool_scope not in {"batch", "region-batch", "region"}:
        raise ValueError("Drop pool scope must be batch, region-batch or region")
    if (
        isinstance(drop_rate, bool)
        or not isinstance(drop_rate, (int, float))
        or not 0 <= float(drop_rate) < 1
    ):
        raise ValueError("Drop rate must be numeric in [0, 1)")
    required = {"site_key", "action"}
    missing = sorted(required - set(expected.columns))
    if missing:
        raise ValueError(f"Drop authority lacks columns: {missing}")

    install_keys: list[str] = []
    seen: set[str] = set()
    for row in expected.itertuples(index=False):
        if _text(getattr(row, "action")).casefold() != "install":
            continue
        site_key = str(getattr(row, "site_key"))
        _site_parts(site_key)
        if site_key not in seen:
            seen.add(site_key)
            install_keys.append(site_key)
    if not install_keys:
        raise ValueError("Drop authority contains no install sites")

    # Reconstruct the fixed engine's left-side batch-input order.  Direct
    # Region/site rows win; explicit ALL rows and unique site fallbacks retain
    # their own source position under the same resolution semantics used by
    # the two consuming rules.
    mapping_items = list(batch_map.items())
    mapping_positions = {str(key): index for index, (key, _) in enumerate(mapping_items)}
    positions_by_site: dict[str, list[int]] = defaultdict(list)
    for index, (key, _) in enumerate(mapping_items):
        _region, separator, site = str(key).partition("|")
        if separator:
            positions_by_site[site].append(index)

    def authority_order(site_key: str) -> tuple[int, str]:
        region, site = _site_parts(site_key)
        direct = mapping_positions.get(site_key)
        if direct is not None:
            return direct, site_key
        fallback = mapping_positions.get(f"all|{site}")
        if fallback is not None:
            return fallback, site_key
        positions = positions_by_site.get(site, ())
        if len(positions) == 1:
            return positions[0], site_key
        # This is defensive only: a site with no resolvable batch is omitted
        # below, just as the fixed engine removes it before Drop.
        return len(mapping_items) + len(install_keys), f"{region}|{site}"

    pools: dict[tuple[str, str], list[str]] = defaultdict(list)
    for site_key in sorted(install_keys, key=authority_order):
        batch = resolve_batch(site_key, batch_map)
        if batch is None:
            continue
        region, _site = _site_parts(site_key)
        canonical_batch = _batch_identity(batch, batch_kind=batch_kind)
        pool = (
            ("", canonical_batch)
            if pool_scope == "batch"
            else (region, canonical_batch)
            if pool_scope == "region-batch"
            else (region, "")
        )
        pools[pool].append(site_key)
    if not pools:
        raise ValueError("Drop authority has no install site with a delivery batch")

    def pool_order(value: tuple[str, str]) -> tuple[Any, ...]:
        region, batch = value
        if pool_scope in {"batch", "region-batch"}:
            # The fixed engine walks batches globally; Region is a stable
            # secondary key when the Prompt splits one batch by Region.
            return (*_natural_identity(batch), region)
        return (region,)

    rng = random.Random(seed)
    dropped: set[str] = set()
    pool_evidence: list[dict[str, Any]] = []
    decimal_rate = Decimal(str(float(drop_rate)))
    for region, batch in sorted(pools, key=pool_order):
        candidates = pools[(region, batch)]
        drop_count = int(
            (Decimal(len(candidates)) * decimal_rate).to_integral_value(
                rounding=ROUND_FLOOR
            )
        )
        chosen = rng.sample(candidates, drop_count) if drop_count else []
        dropped.update(chosen)
        pool_evidence.append(
            {
                "region": region,
                "batch": batch or None,
                "install_pool_sites": len(candidates),
                "drop_sites": drop_count,
                "target_sites": len(candidates) - drop_count,
                "install_site_keys": list(candidates),
                "dropped_site_keys": list(chosen),
            }
        )

    full = frozenset(site for values in pools.values() for site in values)
    dropped_set = frozenset(dropped)
    return SeededDropSelection(
        seed=seed,
        rate=float(drop_rate),
        pool_scope=pool_scope,
        full_install_site_keys=full,
        retained_install_site_keys=frozenset(full - dropped_set),
        dropped_install_site_keys=dropped_set,
        pools=tuple(pool_evidence),
    )


__all__ = ["SeededDropSelection", "compile_seeded_drop_selection"]
