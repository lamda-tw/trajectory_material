from __future__ import annotations

import importlib
from pathlib import Path

import pandas as pd
import pytest

from simulation.ei.core import adapters
from simulation.ei.core.adapters.products import normalize_product


PRODUCT_MODULES = (
    "site_plan",
    "scope_input",
    "master_plan",
    "batch_input",
    "site_material_timeline",
    "final_material",
    "material_substitution",
    "gap",
    "recovered_supply",
    "reuse_by_region",
    "initial_warehouse",
    "new_warehouse",
    "reuse_warehouse",
)


@pytest.mark.parametrize("product", PRODUCT_MODULES)
def test_each_standard_product_owns_a_named_normalize_entrypoint(product) -> None:
    module = importlib.import_module(
        f"simulation.ei.core.adapters.products.{product}"
    )

    assert callable(module.normalize)
    assert module.normalize.__module__ == module.__name__
    assert any(
        name.startswith("Normalized")
        or name.endswith("Payload")
        or name.endswith("Rows")
        for name in module.__all__
    )


def test_public_adapter_is_a_package_and_has_no_parallel_registry() -> None:
    package = Path(adapters.__file__).resolve().parent

    assert Path(adapters.__file__).name == "__init__.py"
    assert not package.with_suffix(".py").exists()
    assert not (package / "registry.py").exists()
    assert (package / "resolver.py").is_file()
    assert (package / "discovery.py").is_file()
    assert (package / "io.py").is_file()


def test_dispatch_is_by_standard_product_role_before_schema_fallback(monkeypatch) -> None:
    module = importlib.import_module(
        "simulation.ei.core.adapters.products.site_plan"
    )
    sentinel = pd.DataFrame({"standard": [1]})

    def fake_normalize(frame, options):
        assert list(frame.columns) == ["raw"]
        assert options == {"contract": "test"}
        return sentinel, ()

    monkeypatch.setattr(module, "normalize", fake_normalize)

    normalized, issues = normalize_product(
        "site_plan",
        "generic",
        pd.DataFrame({"raw": [1]}),
        {"contract": "test"},
    )

    assert normalized is sentinel
    assert issues == ()
