from __future__ import annotations

import math

import numpy as np
import polars as pl
from resistance_core.stats import wilson_interval
from scipy.stats import chi2_contingency

PREDICTORS: tuple[str, ...] = (
    "sex",
    "home_area",
    "ward_type",
    "institution",
    "ward_code",
    "specimen",
)


def cramers_v(chi2: float, n: int, n_rows: int, n_cols: int) -> float:
    denom = n * (min(n_rows, n_cols) - 1)
    if denom <= 0:
        return 0.0
    return math.sqrt(chi2 / denom)


def _chi2(table: np.ndarray) -> tuple[float, float, int]:
    if table.shape[0] < 2 or table.shape[1] < 2:
        return (0.0, 1.0, 0)
    if (
        table.sum() == 0
        or (table.sum(axis=0) == 0).any()
        or (table.sum(axis=1) == 0).any()
    ):
        return (0.0, 1.0, 0)
    stat, p, dof, _ = chi2_contingency(table, correction=False)
    return (float(stat), float(p), int(dof))


def group_rates(df: pl.DataFrame, group_col: str, outcome_col: str) -> pl.DataFrame:
    """Per-group counts and rates for a binary outcome."""
    grouped = (
        df.filter(pl.col(group_col).is_not_null())
        .with_columns(pl.col(outcome_col).cast(pl.Boolean).alias("_outcome"))
        .group_by(group_col)
        .agg(pl.len().alias("n"), pl.col("_outcome").sum().alias("n_pos"))
        .sort(group_col)
    )
    rows = []
    for group, n, n_pos in grouped.iter_rows():
        low, high = wilson_interval(int(n_pos), int(n))
        rows.append(
            {
                "group": str(group),
                "n": int(n),
                "n_pos": int(n_pos),
                "rate": (n_pos / n) if n else 0.0,
                "ci_low": low,
                "ci_high": high,
            }
        )
    return pl.DataFrame(
        rows,
        schema={
            "group": pl.String,
            "n": pl.Int64,
            "n_pos": pl.Int64,
            "rate": pl.Float64,
            "ci_low": pl.Float64,
            "ci_high": pl.Float64,
        },
    )


def _summarise(
    df: pl.DataFrame,
    group_col: str,
    outcome_col: str,
    outcome_label: str,
    stratum: str,
) -> tuple[dict[str, object] | None, list[dict[str, object]]]:
    rates = group_rates(df, group_col, outcome_col)
    if rates.is_empty() or rates.height < 2:
        return None, []

    total = int(rates["n"].sum())
    counts = rates.select("n_pos", "n").to_numpy()
    table = np.column_stack([counts[:, 0], counts[:, 1] - counts[:, 0]])
    chi2, p_value, dof = _chi2(table)
    v = cramers_v(chi2, int(table.sum()), table.shape[0], table.shape[1])

    detail = [
        {
            "outcome": outcome_label,
            "stratum": stratum,
            "predictor": group_col,
            "group": row["group"],
            "n": row["n"],
            "n_pos": row["n_pos"],
            "rate": row["rate"],
            "ci_low": row["ci_low"],
            "ci_high": row["ci_high"],
        }
        for row in rates.iter_rows(named=True)
    ]

    reference = rates.sort("n", descending=True).row(0, named=True)
    rate_values = rates["rate"].to_list()
    summary = {
        "outcome": outcome_label,
        "stratum": stratum,
        "predictor": group_col,
        "n": total,
        "n_groups": rates.height,
        "chi2": chi2,
        "dof": dof,
        "p_value": p_value,
        "cramers_v": v,
        "min_rate": min(rate_values),
        "max_rate": max(rate_values),
        "reference_group": reference["group"],
        "reference_rate": reference["rate"],
    }
    return summary, detail


def correlate_all(
    analytics: pl.DataFrame, ab_analytics: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return (summary, group_detail) correlation frames."""
    summaries: list[dict[str, object]] = []
    details: list[dict[str, object]] = []

    isolate_outcomes = [
        ("flag:esbl", analytics, "esbl"),
        ("flag:mrsa", analytics, "mrsa"),
        ("flag:vre", analytics, "vre"),
        ("flag:cpe", analytics, "cpe"),
    ]
    for label, frame, col in isolate_outcomes:
        for predictor in PREDICTORS:
            summary, detail = _summarise(frame, predictor, col, label, "all")
            if summary:
                summaries.append(summary)
                details.extend(detail)

    for predictor in PREDICTORS:
        summary, detail = _summarise(
            ab_analytics, predictor, "is_r", "resistance:any", "all"
        )
        if summary:
            summaries.append(summary)
            details.extend(detail)

    for antibiotic in sorted(ab_analytics["antibiotic"].unique().to_list()):
        frame = ab_analytics.filter(pl.col("antibiotic") == antibiotic)
        for predictor in PREDICTORS:
            summary, detail = _summarise(
                frame,
                predictor,
                "is_r",
                "resistance:antibiotic",
                antibiotic,
            )
            if summary:
                summaries.append(summary)
                details.extend(detail)

    return (
        pl.DataFrame(
            summaries,
            schema={
                "outcome": pl.String,
                "stratum": pl.String,
                "predictor": pl.String,
                "n": pl.Int64,
                "n_groups": pl.Int64,
                "chi2": pl.Float64,
                "dof": pl.Int64,
                "p_value": pl.Float64,
                "cramers_v": pl.Float64,
                "min_rate": pl.Float64,
                "max_rate": pl.Float64,
                "reference_group": pl.String,
                "reference_rate": pl.Float64,
            },
        ),
        pl.DataFrame(
            details,
            schema={
                "outcome": pl.String,
                "stratum": pl.String,
                "predictor": pl.String,
                "group": pl.String,
                "n": pl.Int64,
                "n_pos": pl.Int64,
                "rate": pl.Float64,
                "ci_low": pl.Float64,
                "ci_high": pl.Float64,
            },
        ),
    )
