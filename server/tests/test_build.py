from __future__ import annotations

import polars as pl

from resistance.build import build_contexts
from resistance.load import load_dataset


def test_days_since_admission_is_derived(dataset_dir) -> None:
    contexts = build_contexts(load_dataset(dataset_dir))
    c1 = contexts.filter(pl.col("culture_id") == "C1").row(0, named=True)
    c3 = contexts.filter(pl.col("culture_id") == "C3").row(0, named=True)
    c2 = contexts.filter(pl.col("culture_id") == "C2").row(0, named=True)
    assert c1["days_since_admission"] == 2
    assert c3["days_since_admission"] == 1
    assert c2["days_since_admission"] is None
