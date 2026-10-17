from __future__ import annotations

import polars as pl
from resistance_analysis.correlate import (
    cramers_v,
    group_rates,
)
from resistance_core.stats import wilson_interval


def test_wilson_interval_matches_known_value() -> None:
    low, high = wilson_interval(5, 10)
    assert abs(low - 0.2366) < 1e-3
    assert abs(high - 0.7634) < 1e-3
    assert wilson_interval(0, 10)[0] == 0.0


def test_cramers_v_perfect_association() -> None:
    assert cramers_v(20.0, 20, 2, 2) == 1.0
    assert cramers_v(0.0, 20, 2, 2) == 0.0


def test_group_rates_counts_and_rates() -> None:
    frame = pl.DataFrame(
        {
            "sex": ["F", "F", "F", "M", "M"],
            "is_r": [True, True, False, False, False],
        }
    )
    rates = group_rates(frame, "sex", "is_r").sort("group")
    rows = {row["group"]: row for row in rates.iter_rows(named=True)}
    assert rows["F"]["n"] == 3
    assert rows["F"]["n_pos"] == 2
    assert abs(rows["F"]["rate"] - 2 / 3) < 1e-9
    assert rows["M"]["rate"] == 0.0
