from __future__ import annotations

import polars as pl

from .load import Dataset


def _age_band_expr(edges: tuple[float, ...]) -> pl.Expr:
    if not edges:
        return pl.lit("Q1")
    expr = pl.when(pl.col("age_years") <= edges[0]).then(pl.lit("Q1"))
    for index, edge in enumerate(edges[1:], start=2):
        expr = expr.when(pl.col("age_years") <= edge).then(pl.lit(f"Q{index}"))
    return expr.otherwise(pl.lit(f"Q{len(edges) + 1}"))


def build_contexts(ds: Dataset) -> pl.DataFrame:
    """Culture-level frame with parsed dates and derived admission offset."""
    return (
        ds.cultures.select(
            "culture_id",
            "patient_id",
            "age_years",
            "sample_date",
            "iso_year",
            "iso_week",
            "ward_code",
            "ward_type",
            "institution",
            "admission_date",
            "specimen",
            "result",
            "n_isolates",
        )
        .with_columns(
            pl.col("sample_date").str.to_date(),
            pl.col("admission_date").str.to_date(),
        )
        .with_columns(
            (pl.col("sample_date") - pl.col("admission_date"))
            .dt.total_days()
            .alias("days_since_admission")
        )
    )


def build_analytics(
    ds: Dataset, age_edges: tuple[float, ...]
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return (contexts, isolate-level analytics) frames."""
    contexts = build_contexts(ds)
    patients = ds.patients.select("patient_id", "sex", "birth_year", "home_area")
    analytics = (
        ds.isolates.join(contexts, on="culture_id", how="left")
        .join(patients, on="patient_id", how="left")
        .with_columns(_age_band_expr(age_edges).alias("age_band"))
    )
    return contexts, analytics


def apply_surveillance(
    analytics: pl.DataFrame, ab_analytics: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Keep only the first isolate per patient x species x specimen (by sample order)."""
    first = (
        analytics.sort("sample_date", "isolate_id")
        .group_by("patient_id", "organism", "specimen", maintain_order=True)
        .agg(pl.col("isolate_id").first().alias("isolate_id"))
    )
    keep = first["isolate_id"].to_list()
    return (
        analytics.filter(pl.col("isolate_id").is_in(keep)),
        ab_analytics.filter(pl.col("isolate_id").is_in(keep)),
    )


def build_susceptibility_analytics(ds: Dataset, contexts: pl.DataFrame) -> pl.DataFrame:
    """Isolate x antibiotic frame with patient/culture context and the R outcome."""
    ab = ds.antibiotics.select("antibiotic_code", "class", "reported_for")
    ctx = contexts.select(
        "culture_id",
        "patient_id",
        "age_years",
        "sample_date",
        "iso_year",
        "iso_week",
        "ward_code",
        "ward_type",
        "institution",
        "specimen",
        "days_since_admission",
    )
    patients = ds.patients.select("patient_id", "sex", "birth_year", "home_area")
    return (
        ds.susceptibility.join(ab, on="antibiotic_code", how="left")
        .join(ctx, on="culture_id", how="left")
        .join(patients, on="patient_id", how="left")
        .with_columns((pl.col("result") == "R").alias("is_r"))
    )
