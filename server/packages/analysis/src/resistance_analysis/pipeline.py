from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import polars as pl
from resistance_core.demographics import age_band_edges as derive_age_band_edges

from . import build, report, structure, wards
from .antibiogram import Antibiogram, build_antibiogram
from .config import Settings
from .correlate import correlate_all
from .deviations import (
    Deviation,
    detect_consistency,
    detect_outliers,
    summarise,
)
from .load import Dataset, load_dataset
from .resistance import attach_resistance_profile


@dataclass
class PipelineResult:
    settings: Settings
    raw: Dataset
    contexts: pl.DataFrame
    analytics: pl.DataFrame
    ab_analytics: pl.DataFrame
    analysis: pl.DataFrame
    ab_analysis: pl.DataFrame
    deviations: list[Deviation]
    deviation_summary: dict[str, Any]
    outliers: list[Deviation]
    outlier_summary: dict[str, Any]
    correlations: pl.DataFrame
    group_rates: pl.DataFrame
    antibiogram: Antibiogram
    age_band_edges: tuple[float, ...]
    document: dict[str, Any]


def _prepare(ds: Dataset, age_edges: tuple[float, ...]):
    contexts, analytics = build.build_analytics(ds, age_edges)
    ab_analytics = build.build_susceptibility_analytics(ds, contexts)
    analytics = attach_resistance_profile(analytics, ab_analytics)
    return contexts, analytics, ab_analytics


def run(settings: Settings, *, write: bool = True) -> PipelineResult:
    raw = load_dataset(settings.data_dir)
    age_edges = derive_age_band_edges(raw.cultures["age_years"].to_list())

    # Read once; every stage below reads from the same records. Deviations and
    # outliers are reported, never applied, so nothing is rebuilt or removed.
    contexts, analytics, ab_analytics = _prepare(raw, age_edges)
    deviations = detect_consistency(raw, ab_analytics)

    # The analysis view applies the surveillance rule; the JSON keeps every record.
    if settings.surveillance:
        analysis, ab_analysis = build.apply_surveillance(analytics, ab_analytics)
    else:
        analysis, ab_analysis = analytics, ab_analytics

    correlations, group_rates = correlate_all(analysis, ab_analysis)

    antibiogram = build_antibiogram(
        contexts,
        analytics,
        ab_analytics,
        raw.patients,
        raw.wards,
        raw.antibiotics,
        settings,
    )
    ward_summaries = wards.build_ward_summaries(
        contexts, analysis, ab_analysis, raw.wards, raw.antibiotics
    )
    deviation_summary = summarise(deviations)
    outliers = detect_outliers(ab_analysis)
    outlier_summary = summarise(outliers)
    document = structure.build_document(
        raw,
        contexts,
        analytics,
        ab_analytics,
        antibiogram,
        ward_summaries,
        deviation_summary,
        outlier_summary,
        settings,
        age_band_edges=age_edges,
    )

    result = PipelineResult(
        settings=settings,
        raw=raw,
        contexts=contexts,
        analytics=analytics,
        ab_analytics=ab_analytics,
        analysis=analysis,
        ab_analysis=ab_analysis,
        deviations=deviations,
        deviation_summary=deviation_summary,
        outliers=outliers,
        outlier_summary=outlier_summary,
        correlations=correlations,
        group_rates=group_rates,
        antibiogram=antibiogram,
        age_band_edges=age_edges,
        document=document,
    )

    if write:
        write_outputs(result)
    return result


def write_outputs(result: PipelineResult) -> None:
    out_dir = result.settings.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    report.write_log(result.deviations, out_dir, "deviations")
    report.write_log(result.outliers, out_dir, "outliers")
    report.write_correlations(result.correlations, result.group_rates, out_dir)
    result.ab_analysis.write_csv(out_dir / "analytics.csv")
    (out_dir / "dataset.json").write_text(
        json.dumps(result.document, ensure_ascii=False, default=str), encoding="utf-8"
    )
    report.write_summary_markdown(
        out_dir,
        result.document["metadata"],  # type: ignore[arg-type]
        result.correlations,
        result.deviation_summary,
        result.outlier_summary,
        result.antibiogram.matrix,
    )


def build_document_only(settings: Settings) -> dict[str, Any]:
    return run(settings, write=False).document


__all__ = ["PipelineResult", "build_document_only", "run", "write_outputs"]
