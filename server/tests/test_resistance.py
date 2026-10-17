from __future__ import annotations

import polars as pl
from resistance_analysis.resistance import attach_resistance_profile


def test_attach_resistance_profile_counts_distinct_classes() -> None:
    analytics = pl.DataFrame(
        {"isolate_id": ["A", "B"], "organism": ["x", "x"]},
        schema={"isolate_id": pl.String, "organism": pl.String},
    )
    ab = pl.DataFrame(
        {
            "isolate_id": ["A", "A", "A", "A", "B"],
            "class": [
                "penicillins",
                "penicillins",
                "cephalosporins",
                "carbapenems",
                "penicillins",
            ],
            "is_r": [True, True, True, False, False],
        }
    )
    result = attach_resistance_profile(analytics, ab).sort("isolate_id")
    rows = {r["isolate_id"]: r for r in result.iter_rows(named=True)}
    assert rows["A"]["n_resistant_classes"] == 2  # penicillins counted once
    assert rows["A"]["n_resistant_tests"] == 3
    assert rows["B"]["n_resistant_classes"] == 0
    assert rows["B"]["n_resistant_tests"] == 0
