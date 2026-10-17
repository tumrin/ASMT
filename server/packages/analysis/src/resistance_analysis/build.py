from __future__ import annotations

import polars as pl

from .load import Dataset


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


def build_analytics(ds: Dataset, contexts: pl.DataFrame) -> pl.DataFrame:
    """Isolate-level frame with patient and culture context."""
    patients = ds.patients.select("patient_id", "sex", "birth_year", "home_area")
    return ds.isolates.join(contexts, on="culture_id", how="left").join(
        patients, on="patient_id", how="left"
    )


def build_susceptibility_analytics(ds: Dataset, contexts: pl.DataFrame) -> pl.DataFrame:
    """Isolate x antibiotic frame with patient/culture context and the S/R outcome."""
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
        .with_columns(
            (pl.col("result") == "R").alias("is_r"),
            (pl.col("result") == "S").alias("is_s"),
        )
    )
