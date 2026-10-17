from __future__ import annotations

from collections import defaultdict
from typing import Any

import polars as pl
from resistance_core.antibiotic_properties import MARKER_FLAGS, marker_codes

BASIS = (
    "volumes from all records; isolates from the first-isolate surveillance view; "
    "flag rates are per organism and use the marker antibiotic denominator present "
    "in susceptibility.csv"
)


def _rate(n_pos: int, n: int) -> float:
    return round(n_pos / n, 4) if n else 0.0


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
    """Per-ward overview: volumes, case mix, organisms and flag rates."""
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
            "basis": BASIS,
        }
    return summaries
