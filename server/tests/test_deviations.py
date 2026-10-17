from __future__ import annotations

import polars as pl
from resistance_analysis.build import build_analytics, build_susceptibility_analytics
from resistance_analysis.deviations import Family, detect_consistency
from resistance_analysis.load import Dataset, load_dataset
from resistance_analysis.resistance import attach_resistance_profile
from resistance_core.demographics import age_band_edges

from tests.conftest import small_frames


def _analytics(ds: Dataset):
    edges = age_band_edges(ds.cultures["age_years"].to_list())
    contexts, analytics = build_analytics(ds, edges)
    ab = build_susceptibility_analytics(ds, contexts)
    return attach_resistance_profile(analytics, ab), ab


def test_consistency_family_finds_injected_anomalies(dataset_dir) -> None:
    ds = load_dataset(dataset_dir)
    _isolates, ab = _analytics(ds)
    deviations = detect_consistency(ds, ab)

    detectors = {d.detector for d in deviations}
    assert {
        "flag_without_marker",
        "flag_susceptibility_contradiction",
        "agent_specimen_mismatch",
        "negative_culture_with_isolates",
    } <= detectors
    assert all(d.family is Family.CONSISTENCY for d in deviations)

    keys = {d.unit_key for d in deviations}
    assert "C5-1:mrsa" in keys  # MRSA on E. coli, no FOX marker
    assert "C2-1:mrsa" in keys  # MRSA but cefoxitin S
    assert "C2-1:MEC" in keys  # urine-only agent on blood
    assert "C4" in keys  # negative culture with an isolate


def test_marker_without_flag_is_limited_to_definitional_flags() -> None:
    frames = small_frames()
    antibiotics = pl.concat(
        [
            frames["antibiotics.csv"],
            pl.DataFrame(
                {
                    "antibiotic": ["cefuroxime", "meropenem"],
                    "antibiotic_code": ["CXM", "MEM"],
                    "antibiotic_fi": ["kefuroksiimi", "meropeneemi"],
                    "class": ["cephalosporins 2nd gen", "carbapenems"],
                    "reported_for": ["all", "all"],
                }
            ),
        ]
    )
    susceptibility = pl.concat(
        [
            frames["susceptibility.csv"],
            pl.DataFrame(
                {
                    "isolate_id": ["C1-1", "C1-1"],
                    "culture_id": ["C1", "C1"],
                    "organism": ["Escherichia coli", "Escherichia coli"],
                    "antibiotic": ["cefuroxime", "meropenem"],
                    "antibiotic_code": ["CXM", "MEM"],
                    "antibiotic_fi": ["kefuroksiimi", "meropeneemi"],
                    "result": ["R", "R"],
                    "guideline": ["EUCAST 2023", "EUCAST 2023"],
                }
            ),
        ]
    )
    # mrsa=0 with a resistant cefoxitin screen: a real contradiction.
    isolates = frames["isolates.csv"].with_columns(
        pl.when(pl.col("isolate_id") == "C2-1")
        .then(0)
        .otherwise(pl.col("mrsa"))
        .alias("mrsa")
    )
    susceptibility = susceptibility.with_columns(
        pl.when((pl.col("isolate_id") == "C2-1") & (pl.col("antibiotic_code") == "FOX"))
        .then(pl.lit("R"))
        .otherwise(pl.col("result"))
        .alias("result")
    )
    ds = Dataset(
        patients=frames["patients.csv"],
        cultures=frames["cultures.csv"],
        isolates=isolates,
        susceptibility=susceptibility,
        antibiotics=antibiotics,
        wards=frames["wards.csv"],
    )
    _isolates, ab = _analytics(ds)
    markers = [
        d for d in detect_consistency(ds, ab) if d.detector == "marker_without_flag"
    ]
    keys = {d.unit_key for d in markers}
    assert "C2-1:mrsa" in keys
    # Cefuroxime / meropenem resistance does not imply ESBL / CPE.
    assert not any(key.endswith((":esbl", ":cpe")) for key in keys)


def test_consistency_consistent_data_finds_nothing(dataset_dir) -> None:
    ds = load_dataset(dataset_dir)

    cultures = ds.cultures.with_columns(
        pl.when(pl.col("culture_id") == "C2")
        .then(pl.lit("2024-01-01"))
        .when(pl.col("culture_id") == "C5")
        .then(pl.lit("2024-01-01"))
        .when(pl.col("culture_id") == "C3")
        .then(None)
        .otherwise(pl.col("admission_date"))
        .alias("admission_date")
    ).filter(pl.col("culture_id") != "C4")
    isolates = ds.isolates.filter(pl.col("isolate_id") != "C4-1").with_columns(
        pl.when(pl.col("isolate_id").is_in(["C5-1", "C2-1"]))
        .then(0)
        .otherwise(pl.col("mrsa"))
        .alias("mrsa")
    )
    susceptibility = ds.susceptibility.filter(
        (pl.col("isolate_id") != "C4-1")
        & ~((pl.col("isolate_id") == "C2-1") & (pl.col("antibiotic_code") == "MEC"))
    )
    ds_consistent = Dataset(
        patients=ds.patients,
        cultures=cultures,
        isolates=isolates,
        susceptibility=susceptibility,
        antibiotics=ds.antibiotics,
        wards=ds.wards,
    )
    _isolates, ab = _analytics(ds_consistent)
    assert detect_consistency(ds_consistent, ab) == []
