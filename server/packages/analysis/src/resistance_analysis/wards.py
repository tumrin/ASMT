from __future__ import annotations

from collections import defaultdict
from typing import Any

import polars as pl
from resistance_core.antibiotic_properties import (
    MARKER_FLAGS,
    marker_codes,
    metadata_by_code,
)
from resistance_core.stats import wilson_interval

BASIS = (
    "volumes from all records; isolates and resistance rates from the "
    "first-isolate surveillance view; flag rates are per organism and use the "
    "marker antibiotic denominator present in susceptibility.csv; screens are "
    "excluded from treatment lists"
)


def _rate(n_pos: int, n: int) -> float:
    return round(n_pos / n, 4) if n else 0.0


def _antibiotic_entry(row: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    meta = metadata[row["antibiotic_code"]]
    n = int(row["n"])
    n_pos = int(row["n_pos"])
    low, high = wilson_interval(n_pos, n)
    return {
        "antibiotic": row["antibiotic"],
        "antibiotic_code": row["antibiotic_code"],
        "class": row["class"],
        "specimen": row["specimen"],
        "reported_for": meta.reported_for,
        "role": meta.role,
        "n": n,
        "n_pos": n_pos,
        "rate": _rate(n_pos, n),
        "ci_low": round(low, 4),
        "ci_high": round(high, 4),
    }


def _tiered_by_specimen(
    rows: list[dict[str, Any]], metadata: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        entry = _antibiotic_entry(row, metadata)
        if entry["role"] == "screen":
            continue
        grouped[row["specimen"]].append(entry)
    for entries in grouped.values():
        entries.sort(key=lambda entry: (entry["rate"], entry["antibiotic"]))
    return dict(grouped)


def _build_antibiogram(
    ab_analysis: pl.DataFrame, metadata: dict[str, Any]
) -> dict[str, dict[str, dict[str, list[dict[str, Any]]]]]:
    if "organism" not in ab_analysis.columns:
        return {}
    grouped: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    rows = (
        ab_analysis.group_by(
            "ward_code",
            "specimen",
            "organism",
            "antibiotic",
            "antibiotic_code",
            "class",
        )
        .agg(pl.len().alias("n"), pl.col("is_r").sum().alias("n_pos"))
        .sort("ward_code", "specimen", "organism", "antibiotic")
    )
    for row in rows.iter_rows(named=True):
        entry = _antibiotic_entry(row, metadata)
        if entry["role"] == "screen":
            continue
        grouped[row["ward_code"]][row["specimen"]][row["organism"]].append(entry)
    for specimens in grouped.values():
        for organisms in specimens.values():
            for entries in organisms.values():
                entries.sort(key=lambda entry: (entry["rate"], entry["antibiotic"]))
    return {
        ward: {specimen: dict(organisms) for specimen, organisms in specimens.items()}
        for ward, specimens in grouped.items()
    }


def _flag_rates_by_organism(
    analysis: pl.DataFrame,
    ab_analysis: pl.DataFrame,
    markers: dict[str, tuple[str, ...]],
) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
    """Per organism and flag: denominator = isolates with the marker tested."""
    result: dict[str, dict[str, dict[str, dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for flag in MARKER_FLAGS:
        codes = markers.get(flag, ())
        if not codes:
            continue
        flagged = analysis.filter(pl.col(flag) == 1)
        if flagged.is_empty():
            continue
        positive_organisms = set(flagged["organism"].unique().to_list())
        tested = ab_analysis.filter(pl.col("antibiotic_code").is_in(codes)).select(
            "ward_code", "isolate_id"
        )
        if tested.is_empty():
            continue
        candidates = analysis.join(tested, on=["ward_code", "isolate_id"], how="semi")
        grouped = candidates.group_by("ward_code", "organism").agg(
            pl.len().alias("n"), pl.col(flag).sum().alias("n_pos")
        )
        for row in grouped.iter_rows(named=True):
            if row["organism"] not in positive_organisms:
                continue
            n = int(row["n"])
            n_pos = int(row["n_pos"])
            result[row["ward_code"]][row["organism"]][flag] = {
                "n": n,
                "n_pos": n_pos,
                "rate": _rate(n_pos, n),
                "marker_antibiotic_codes": list(codes),
            }
    return {
        ward: {organism: dict(flags) for organism, flags in organisms.items()}
        for ward, organisms in result.items()
    }


def build_ward_summaries(
    contexts: pl.DataFrame,
    analysis: pl.DataFrame,
    ab_analysis: pl.DataFrame,
    wards_meta: pl.DataFrame,
    antibiotics: pl.DataFrame,
    top_n: int = 10,
) -> dict[str, dict[str, Any]]:
    """Per-ward overview: volumes, case mix, organisms and resistance rates."""
    metadata = metadata_by_code(antibiotics)
    markers = marker_codes(antibiotics)
    ward_meta = {row["ward_code"]: row for row in wards_meta.iter_rows(named=True)}

    volume = {
        row["ward_code"]: row
        for row in contexts.group_by("ward_code")
        .agg(
            pl.col("patient_id").n_unique().alias("patients"),
            pl.len().alias("cultures"),
            pl.col("sample_date").min().alias("start"),
            pl.col("sample_date").max().alias("end"),
        )
        .iter_rows(named=True)
    }

    isolate_counts = {
        row["ward_code"]: int(row["n"])
        for row in analysis.group_by("ward_code")
        .agg(pl.len().alias("n"))
        .iter_rows(named=True)
    }

    susceptibility_counts = {
        row["ward_code"]: row["n"]
        for row in ab_analysis.group_by("ward_code")
        .agg(pl.len().alias("n"))
        .iter_rows(named=True)
    }

    by_specimen: dict[str, dict[str, int]] = defaultdict(dict)
    for row in (
        contexts.group_by("ward_code", "specimen")
        .agg(pl.len().alias("n"))
        .iter_rows(named=True)
    ):
        by_specimen[row["ward_code"]][row["specimen"]] = row["n"]

    by_result: dict[str, dict[str, int]] = defaultdict(dict)
    for row in (
        contexts.group_by("ward_code", "result")
        .agg(pl.len().alias("n"))
        .iter_rows(named=True)
    ):
        by_result[row["ward_code"]][row["result"]] = row["n"]

    organisms: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in (
        analysis.group_by("ward_code", "organism")
        .agg(pl.len().alias("n"))
        .sort("n", descending=True)
        .iter_rows(named=True)
    ):
        organisms[row["ward_code"]].append(row)

    antibiotics_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in (
        ab_analysis.group_by(
            "ward_code", "specimen", "antibiotic", "antibiotic_code", "class"
        )
        .agg(pl.len().alias("n"), pl.col("is_r").sum().alias("n_pos"))
        .sort("n", descending=True)
        .iter_rows(named=True)
    ):
        antibiotics_rows[row["ward_code"]].append(row)

    antibiogram = _build_antibiogram(ab_analysis, metadata)
    flag_rates = _flag_rates_by_organism(analysis, ab_analysis, markers)

    summaries: dict[str, dict[str, Any]] = {}
    for ward_code, vol in volume.items():
        meta = ward_meta.get(ward_code, {})
        total_isolates = isolate_counts.get(ward_code, 0)
        summaries[ward_code] = {
            "ward_code": ward_code,
            "ward_fi": meta.get("ward_fi"),
            "ward_en": meta.get("ward_en"),
            "ward_type": meta.get("ward_type"),
            "institution": meta.get("institution"),
            "date_range": {"start": str(vol["start"]), "end": str(vol["end"])},
            "counts": {
                "patients": int(vol["patients"]),
                "cultures": int(vol["cultures"]),
                "isolates": total_isolates,
                "susceptibility_results": int(susceptibility_counts.get(ward_code, 0)),
            },
            "cultures_by_specimen": by_specimen.get(ward_code, {}),
            "cultures_by_result": by_result.get(ward_code, {}),
            "organisms": [
                {
                    "organism": row["organism"],
                    "isolates": int(row["n"]),
                    "share": _rate(int(row["n"]), total_isolates),
                }
                for row in organisms.get(ward_code, [])[:top_n]
            ],
            "flag_rates_by_organism": flag_rates.get(ward_code, {}),
            "resistance_by_antibiotic": _tiered_by_specimen(
                antibiotics_rows.get(ward_code, []), metadata
            ),
            "antibiogram": antibiogram.get(ward_code, {}),
            "basis": BASIS,
        }
    return summaries
