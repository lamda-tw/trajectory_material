"""Precompiled delivery-batch lookup shared by EI business rules."""

from __future__ import annotations

from collections.abc import Iterator, Mapping

import pandas as pd


class QuestionDataConflict(ValueError):
    """Question authorities contradict one another before candidate scoring."""


def _identity(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().casefold()


def _column(frame: pd.DataFrame, *aliases: str) -> str | None:
    columns = {_identity(value): str(value) for value in frame.columns}
    for alias in aliases:
        if _identity(alias) in columns:
            return columns[_identity(alias)]
    return None


def assert_question_region_consistency(
    scope_input: pd.DataFrame,
    batch_input: pd.DataFrame,
) -> None:
    """Reject overlapping site identities whose two authorities disagree.

    Region-less ``ALL`` rows do not assert a competing region.  The check is
    deliberately candidate-independent: a mismatch is a question-data error,
    not a reason to penalize an agent output or to use region fallback.
    """

    resolved: dict[str, tuple[str, str]] = {}
    for label, frame in (("scope_input", scope_input), ("batch_input", batch_input)):
        site_column = _column(
            frame,
            "site_id",
            "site_name",
            "site id",
            "site id radio",
            "du id",
            "*du id",
        )
        region_column = _column(frame, "region", "区域")
        if site_column is None or region_column is None:
            raise QuestionDataConflict(
                f"QUESTION_DATA_CONFLICT: {label} lacks site/region preflight fields"
            )
        resolved[label] = (site_column, region_column)

    def regions(frame: pd.DataFrame, columns: tuple[str, str]) -> dict[str, set[str]]:
        result: dict[str, set[str]] = {}
        for site_value, region_value in frame.loc[:, list(columns)].itertuples(
            index=False,
            name=None,
        ):
            site = _identity(site_value)
            region = _identity(region_value)
            if not site or region in {"", "all"}:
                continue
            result.setdefault(site, set()).add(region)
        return result

    scope_regions = regions(scope_input, resolved["scope_input"])
    batch_regions = regions(batch_input, resolved["batch_input"])
    conflicts = [
        {
            "site_id": site,
            "scope_regions": sorted(scope_regions[site]),
            "batch_regions": sorted(batch_regions[site]),
        }
        for site in sorted(scope_regions.keys() & batch_regions.keys())
        if scope_regions[site] != batch_regions[site]
    ]
    if conflicts:
        raise QuestionDataConflict(
            "QUESTION_DATA_CONFLICT: scope_input and batch_input Region disagree "
            f"for {len(conflicts)} overlapping sites; sample={conflicts[:20]}"
        )


class BatchLookup(Mapping[str, str]):
    """Immutable mapping with O(1) region fallback and unique-site lookup.

    Resolution preserves the existing EI semantics in this order: exact
    region/site, explicit ``all`` region, then a batch that is unique across
    every region for the same site.  Ambiguous cross-region batches resolve to
    ``None``.
    """

    def __init__(self, mapping: Mapping[str, str]) -> None:
        self._mapping = dict(mapping)
        by_site: dict[str, str | None] = {}
        for key, batch in self._mapping.items():
            _region, separator, site = str(key).partition("|")
            if not separator:
                continue
            if site not in by_site:
                by_site[site] = batch
            elif by_site[site] != batch:
                by_site[site] = None
        self._by_site = by_site

    def __getitem__(self, key: str) -> str:
        return self._mapping[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping)

    def __len__(self) -> int:
        return len(self._mapping)

    def resolve(self, site_key: str) -> str | None:
        direct = self._mapping.get(site_key)
        if direct is not None:
            return direct
        _region, separator, site = str(site_key).partition("|")
        if not separator:
            return None
        fallback = self._mapping.get(f"all|{site}")
        if fallback is not None:
            return fallback
        return self._by_site.get(site)

    def as_dict(self) -> dict[str, str]:
        """Return a copy for evidence serialization or compatibility callers."""

        return dict(self._mapping)


def compile_batch_lookup(mapping: Mapping[str, str]) -> BatchLookup:
    if isinstance(mapping, BatchLookup):
        return mapping
    return BatchLookup(mapping)


def resolve_batch(site_key: str, mapping: Mapping[str, str]) -> str | None:
    """Resolve with the precompiled path, retaining compatibility for mappings."""

    if isinstance(mapping, BatchLookup):
        return mapping.resolve(site_key)
    return BatchLookup(mapping).resolve(site_key)


__all__ = [
    "BatchLookup",
    "QuestionDataConflict",
    "assert_question_region_consistency",
    "compile_batch_lookup",
    "resolve_batch",
]
