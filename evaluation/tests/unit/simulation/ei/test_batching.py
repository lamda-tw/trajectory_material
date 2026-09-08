from simulation.ei.rules.ei_standard.batching import (
    BatchLookup,
    compile_batch_lookup,
)


def test_batch_lookup_preserves_exact_all_and_unique_site_precedence() -> None:
    lookup = compile_batch_lookup(
        {
            "north|exact": "B1",
            "all|fallback": "B2",
            "south|unique": "B3",
        }
    )

    assert isinstance(lookup, BatchLookup)
    assert lookup.resolve("north|exact") == "B1"
    assert lookup.resolve("west|fallback") == "B2"
    assert lookup.resolve("west|unique") == "B3"
    assert lookup.resolve("west|missing") is None


def test_batch_lookup_rejects_ambiguous_cross_region_fallback() -> None:
    lookup = compile_batch_lookup(
        {
            "north|shared": "B1",
            "south|shared": "B2",
        }
    )

    assert lookup.resolve("west|shared") is None
    assert lookup.resolve("north|shared") == "B1"


def test_batch_lookup_is_a_read_only_mapping_with_stable_copy() -> None:
    source = {"north|site": "B1"}
    lookup = compile_batch_lookup(source)
    source["north|site"] = "changed"

    assert dict(lookup) == {"north|site": "B1"}
    assert lookup.as_dict() == {"north|site": "B1"}
