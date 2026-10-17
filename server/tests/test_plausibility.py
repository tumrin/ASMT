from __future__ import annotations

from collections.abc import Callable

import polars as pl
from resistance_analysis.build import build_analytics, build_susceptibility_analytics
from resistance_analysis.deviations import detect_consistency
from resistance_analysis.load import Dataset
from resistance_core.demographics import age_band_edges

from tests.conftest import small_frames


def _dataset(frames: dict[str, pl.DataFrame]) -> Dataset:
    return Dataset(
        patients=frames["patients.csv"],
        cultures=frames["cultures.csv"],
        isolates=frames["isolates.csv"],
        susceptibility=frames["susceptibility.csv"],
        antibiotics=frames["antibiotics.csv"],
        wards=frames["wards.csv"],
    )


def _detectors(frames: dict[str, pl.DataFrame]) -> set[str]:
    ds = _dataset(frames)
    edges = age_band_edges(ds.cultures["age_years"].to_list())
    contexts, _ = build_analytics(ds, edges)
    ab = build_susceptibility_analytics(ds, contexts)
    return {d.detector for d in detect_consistency(ds, ab)}


def _with_frame(
    frames: dict[str, pl.DataFrame],
    name: str,
    mutator: Callable[[pl.DataFrame], pl.DataFrame],
) -> dict[str, pl.DataFrame]:
    mutated = dict(frames)
    mutated[name] = mutator(frames[name])
    return mutated


def _cases() -> list[tuple[str, dict[str, pl.DataFrame]]]:
    base = small_frames()
    return [
        (
            "duplicate_susceptibility_key",
            _with_frame(
                base,
                "susceptibility.csv",
                lambda frame: frame.vstack(frame.head(1)),
            ),
        ),
        (
            "week_year_mismatch",
            _with_frame(
                base,
                "cultures.csv",
                lambda frame: frame.with_columns(
                    pl.when(pl.col("culture_id") == "C1")
                    .then(99)
                    .otherwise(pl.col("iso_week"))
                    .alias("iso_week")
                ),
            ),
        ),
        (
            "age_birth_year_mismatch",
            _with_frame(
                base,
                "patients.csv",
                lambda frame: frame.with_columns(
                    pl.when(pl.col("patient_id") == "P1")
                    .then(1900)
                    .otherwise(pl.col("birth_year"))
                    .alias("birth_year")
                ),
            ),
        ),
        (
            "admission_after_sample",
            _with_frame(
                base,
                "cultures.csv",
                lambda frame: frame.with_columns(
                    pl.when(pl.col("culture_id") == "C1")
                    .then(pl.lit("2024-06-01"))
                    .otherwise(pl.col("admission_date"))
                    .alias("admission_date")
                ),
            ),
        ),
        (
            "admission_date_presence",
            _with_frame(
                base,
                "cultures.csv",
                lambda frame: frame.with_columns(
                    pl.when(pl.col("culture_id") == "C1")
                    .then(None)
                    .otherwise(pl.col("admission_date"))
                    .alias("admission_date")
                ),
            ),
        ),
        (
            "culture_ward_metadata_mismatch",
            _with_frame(
                base,
                "cultures.csv",
                lambda frame: frame.with_columns(
                    pl.when(pl.col("culture_id") == "C1")
                    .then(pl.lit("Väärä osasto"))
                    .otherwise(pl.col("ward_fi"))
                    .alias("ward_fi")
                ),
            ),
        ),
        (
            "specimen_label_mismatch",
            _with_frame(
                base,
                "cultures.csv",
                lambda frame: frame.with_columns(
                    pl.when(pl.col("culture_id") == "C1")
                    .then(pl.lit("vaara"))
                    .otherwise(pl.col("specimen_fi"))
                    .alias("specimen_fi")
                ),
            ),
        ),
        (
            "quantity_format_invalid",
            _with_frame(
                base,
                "isolates.csv",
                lambda frame: frame.with_columns(
                    pl.when(pl.col("isolate_id") == "C1-1")
                    .then(pl.lit("++"))
                    .otherwise(pl.col("quantity"))
                    .alias("quantity")
                ),
            ),
        ),
        (
            "unknown_result_value",
            _with_frame(
                base,
                "cultures.csv",
                lambda frame: frame.with_columns(
                    pl.when(pl.col("culture_id") == "C1")
                    .then(pl.lit("weird"))
                    .otherwise(pl.col("result"))
                    .alias("result")
                ),
            ),
        ),
        (
            "duplicate_isolate_no",
            _with_frame(
                base,
                "isolates.csv",
                lambda frame: frame.vstack(frame.head(1)),
            ),
        ),
        (
            "susceptibility_organism_mismatch",
            _with_frame(
                base,
                "susceptibility.csv",
                lambda frame: frame.with_columns(
                    pl.when(pl.col("isolate_id") == "C2-1")
                    .then(pl.lit("Escherichia coli"))
                    .otherwise(pl.col("organism"))
                    .alias("organism")
                ),
            ),
        ),
        (
            "unknown_guideline",
            _with_frame(
                base,
                "susceptibility.csv",
                lambda frame: frame.with_columns(
                    pl.when(pl.col("isolate_id") == "C1-1")
                    .then(pl.lit("CLSI 2020"))
                    .otherwise(pl.col("guideline"))
                    .alias("guideline")
                ),
            ),
        ),
    ]


def test_each_plausibility_check_fires_on_its_violation() -> None:
    for detector, frames in _cases():
        assert detector in _detectors(frames), detector
