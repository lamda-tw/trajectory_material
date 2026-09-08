from __future__ import annotations

import pandas as pd

from simulation.ei.core.adapters.products.scope_input import normalize


def test_scope_input_included_years_keeps_y1_and_blank_with_source_rows() -> None:
    source = pd.DataFrame(
        {
            "*DU ID": ["S1", "S2", "S3", "S4"],
            "Region": ["R1"] * 4,
            "*物料编码": ["A", "B", "C", "D"],
            "*数量": [1, 1, 1, 1],
            "Year": ["Y1", "", None, "Y2"],
        }
    )

    normalized, issues = normalize(
        source,
        {
            "included_years": ["Y1", ""],
            "_effective_delivery": {"o2_scope_material_mode": "raw"},
        },
    )

    assert issues == ()
    assert normalized["site_id"].tolist() == ["S1", "S2", "S3"]
    assert normalized["source_row"].tolist() == [2, 3, 4]

