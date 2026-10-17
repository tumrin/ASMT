from __future__ import annotations

import polars as pl
from resistance_analysis.deviations import Family
from resistance_analysis.deviations.outliers import detect, funnel_limits


def _ward_frame() -> pl.DataFrame:
    rows = []
    for ward, resistant in (("WARD1", 50), ("WARD2", 0), ("WARD3", 25)):
        for index in range(100):
            rows.append(
                {
                    "organism": "Escherichia coli",
                    "antibiotic": "ampicillin",
                    "antibiotic_code": "AMP",
                    "specimen": "urine",
                    "ward_code": ward,
                    "ward_type": "in",
                    "is_r": index < resistant,
                }
            )
    return pl.DataFrame(rows)


def test_funnel_limits_widen_as_n_shrinks() -> None:
    tight = funnel_limits(0.2, 1000)
    wide = funnel_limits(0.2, 10)
    assert (tight[1] - tight[0]) < (wide[1] - wide[0])


def test_ward_rate_outlier_flags_both_directions() -> None:
    deviations = detect(_ward_frame())
    keys = {d.unit_key for d in deviations if d.detector == "ward_rate_outlier"}
    assert "Escherichia coli|ampicillin|urine|WARD1" in keys
    assert "Escherichia coli|ampicillin|urine|WARD2" in keys
    assert "Escherichia coli|ampicillin|urine|WARD3" not in keys


def test_outliers_are_statistical_and_report_only() -> None:
    deviations = detect(_ward_frame())
    assert deviations
    assert all(d.family is Family.STATISTICAL for d in deviations)
    assert all(d.severity.value == "warning" for d in deviations)


def _weekly_frame() -> pl.DataFrame:
    rows = []
    for week in range(1, 12):
        resistant = 30 if week == 11 else 3
        for index in range(30):
            rows.append(
                {
                    "organism": "Escherichia coli",
                    "antibiotic": "ampicillin",
                    "antibiotic_code": "AMP",
                    "specimen": "urine",
                    "iso_year": 2024,
                    "iso_week": week,
                    "is_r": index < resistant,
                }
            )
    return pl.DataFrame(rows)


def test_weekly_rate_outlier_flags_a_spike() -> None:
    deviations = detect(_weekly_frame())
    weekly = [d for d in deviations if d.detector == "weekly_rate_outlier"]
    assert any(d.unit_key.endswith("2024-W11") for d in weekly)
    assert all(not d.unit_key.endswith("2024-W01") for d in weekly)


def test_weekly_comparison_respects_the_reporting_floor() -> None:
    frame = pl.DataFrame(
        {
            "organism": ["Escherichia coli"],
            "antibiotic": ["ampicillin"],
            "antibiotic_code": ["AMP"],
            "specimen": ["urine"],
            "iso_year": [2024],
            "iso_week": [1],
            "is_r": [True],
        }
    )
    assert not [d for d in detect(frame) if d.detector == "weekly_rate_outlier"]
