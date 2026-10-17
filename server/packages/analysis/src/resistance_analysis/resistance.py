from __future__ import annotations

import polars as pl


def attach_resistance_profile(
    analytics: pl.DataFrame, ab_analytics: pl.DataFrame
) -> pl.DataFrame:
    """Add `n_resistant_classes` and `n_resistant_tests` to isolates.

    Both are counts derived from the dataset. No MDR cutoff is applied.
    """
    resistant_classes = (
        ab_analytics.filter(pl.col("is_r"))
        .group_by("isolate_id")
        .agg(
            pl.col("class").n_unique().alias("n_resistant_classes"),
            pl.len().alias("n_resistant_tests"),
        )
    )
    return analytics.join(resistant_classes, on="isolate_id", how="left").with_columns(
        pl.col("n_resistant_classes").fill_null(0).cast(pl.Int32),
        pl.col("n_resistant_tests").fill_null(0).cast(pl.Int32),
    )
