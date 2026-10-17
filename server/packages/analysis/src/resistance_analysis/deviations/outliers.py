from __future__ import annotations

import math

import polars as pl
from resistance_core.stats import Z_975

from .models import Deviation, Family, Severity, make_deviation

WARD_RATE_OUTLIER = "ward_rate_outlier"
WEEKLY_RATE_OUTLIER = "weekly_rate_outlier"

UNIT_WARD_RATE = "ward_rate"
UNIT_WEEK_RATE = "week_rate"

# A weekly cell is only compared when it holds enough isolates to be reported at
# all. This is the surveillance reporting floor in the README (>= 30 isolates);
# it keeps the 95% level from flagging every one-isolate week.
TEMPORAL_REPORTING_FLOOR = 30


def funnel_limits(rate: float, n: int, z: float = Z_975) -> tuple[float, float]:
    """Binomial control limits around a reference rate at the given n."""
    if n <= 0:
        return (0.0, 1.0)
    half = z * math.sqrt(rate * (1.0 - rate) / n)
    return (max(0.0, rate - half), min(1.0, rate + half))


def _dev(
    detector: str,
    unit_type: str,
    unit_key: str,
    severity: Severity,
    detail: dict[str, object],
) -> Deviation:
    return make_deviation(
        Family.STATISTICAL,
        detector,
        unit_type,
        unit_key,
        "resistance_rate",
        f"inside the 95% funnel of the reference rate {detail['reference_rate']:.4f}",
        f"rate {detail['rate']:.4f} (n={detail['n']})",
        f"z={Z_975}",
        severity,
        **detail,
    )


def _ward_rate_outliers(ab_analysis: pl.DataFrame) -> list[Deviation]:
    keys = ["organism", "antibiotic", "antibiotic_code", "specimen", "ward_code"]
    if "ward_type" not in ab_analysis.columns:
        return []
    keys.append("ward_type")
    grouped = (
        ab_analysis.group_by(keys)
        .agg(pl.len().alias("n"), pl.col("is_r").sum().alias("k"))
        .sort(*keys)
    )
    reference = grouped.group_by("organism", "antibiotic", "specimen", "ward_type").agg(
        pl.col("k").sum().alias("ref_k"),
        pl.col("n").sum().alias("ref_n"),
    )
    joined = grouped.join(
        reference, on=["organism", "antibiotic", "specimen", "ward_type"], how="left"
    )

    deviations: list[Deviation] = []
    for row in joined.iter_rows(named=True):
        n = int(row["n"])
        rate = row["k"] / n
        reference_rate = row["ref_k"] / row["ref_n"]
        low, high = funnel_limits(reference_rate, n)
        if low <= rate <= high:
            continue
        detail: dict[str, object] = {
            "organism": row["organism"],
            "antibiotic": row["antibiotic"],
            "specimen": row["specimen"],
            "ward_code": row["ward_code"],
            "ward_type": row["ward_type"],
            "n": n,
            "k": int(row["k"]),
            "rate": round(rate, 4),
            "reference_rate": round(reference_rate, 4),
            "reference_n": int(row["ref_n"]),
            "ci_low": round(low, 4),
            "ci_high": round(high, 4),
        }
        deviations.append(
            _dev(
                WARD_RATE_OUTLIER,
                UNIT_WARD_RATE,
                "|".join(
                    (
                        row["organism"],
                        row["antibiotic"],
                        row["specimen"],
                        row["ward_code"],
                    )
                ),
                Severity.WARNING,
                detail,
            )
        )
    return deviations


def _weekly_rate_outliers(ab_analysis: pl.DataFrame) -> list[Deviation]:
    required = {"organism", "antibiotic", "specimen", "iso_year", "iso_week"}
    if not required.issubset(ab_analysis.columns):
        return []
    keys = ["organism", "antibiotic", "specimen", "iso_year", "iso_week"]
    grouped = (
        ab_analysis.group_by(keys)
        .agg(pl.len().alias("n"), pl.col("is_r").sum().alias("k"))
        .sort(*keys)
    )
    reference = ab_analysis.group_by("organism", "antibiotic", "specimen").agg(
        pl.col("is_r").sum().alias("ref_k"),
        pl.len().alias("ref_n"),
    )
    joined = grouped.join(
        reference, on=["organism", "antibiotic", "specimen"], how="left"
    ).filter(pl.col("n") >= TEMPORAL_REPORTING_FLOOR)

    deviations: list[Deviation] = []
    for row in joined.iter_rows(named=True):
        n = int(row["n"])
        rate = row["k"] / n
        reference_rate = row["ref_k"] / row["ref_n"]
        low, high = funnel_limits(reference_rate, n)
        if low <= rate <= high:
            continue
        week = f"{row['iso_year']}-W{row['iso_week']:02d}"
        detail: dict[str, object] = {
            "organism": row["organism"],
            "antibiotic": row["antibiotic"],
            "specimen": row["specimen"],
            "week": week,
            "n": n,
            "k": int(row["k"]),
            "rate": round(rate, 4),
            "reference_rate": round(reference_rate, 4),
            "reference_n": int(row["ref_n"]),
            "ci_low": round(low, 4),
            "ci_high": round(high, 4),
        }
        deviations.append(
            _dev(
                WEEKLY_RATE_OUTLIER,
                UNIT_WEEK_RATE,
                "|".join((row["organism"], row["antibiotic"], row["specimen"], week)),
                Severity.WARNING,
                detail,
            )
        )
    return deviations


def detect(ab_analysis: pl.DataFrame) -> list[Deviation]:
    """Statistical outliers over the surveillance view, never applied to the data."""
    return [
        *_ward_rate_outliers(ab_analysis),
        *_weekly_rate_outliers(ab_analysis),
    ]
