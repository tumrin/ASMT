from __future__ import annotations

import polars as pl
from resistance_analysis.build import build_contexts
from resistance_analysis.load import load_dataset
from resistance_core.demographics import age_band_edges


def test_age_bands_are_derived_from_observed_ages() -> None:
    edges = age_band_edges([0, 10, 20, 30, 40, 50, 60, 70, 80, 90])
    assert len(edges) == 4
    assert edges == tuple(sorted(edges))


def test_days_since_admission_is_derived(dataset_dir) -> None:
    contexts = build_contexts(load_dataset(dataset_dir))
    c1 = contexts.filter(pl.col("culture_id") == "C1").row(0, named=True)
    c3 = contexts.filter(pl.col("culture_id") == "C3").row(0, named=True)
    c2 = contexts.filter(pl.col("culture_id") == "C2").row(0, named=True)
    assert c1["days_since_admission"] == 2
    assert c3["days_since_admission"] == 1
    assert c2["days_since_admission"] is None
