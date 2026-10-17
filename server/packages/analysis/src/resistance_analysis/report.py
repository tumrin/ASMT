from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from .deviations import Deviation, to_frame
from .deviations.outliers import TEMPORAL_REPORTING_FLOOR


def write_log(deviations: list[Deviation], out_dir: Path, name: str) -> pl.DataFrame:
    frame = to_frame(deviations)
    frame.write_csv(out_dir / f"{name}.csv")
    with (out_dir / f"{name}.jsonl").open("w", encoding="utf-8") as handle:
        for row in frame.iter_rows(named=True):
            handle.write(json.dumps(row, default=str) + "\n")
    return frame


def write_correlations(
    correlations: pl.DataFrame, group_rates: pl.DataFrame, out_dir: Path
) -> None:
    report_dir = out_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    correlations.write_csv(report_dir / "correlations_summary.csv")
    group_rates.write_csv(report_dir / "group_rates.csv")


def _top_correlations(correlations: pl.DataFrame, limit: int = 15) -> pl.DataFrame:
    if correlations.is_empty():
        return correlations
    return (
        correlations.filter(pl.col("n_groups") >= 2)
        .sort("cramers_v", descending=True)
        .head(limit)
        .select(
            "outcome",
            "stratum",
            "predictor",
            "n",
            "n_groups",
            "cramers_v",
            "p_value",
            "min_rate",
            "max_rate",
        )
    )


def _markdown_table(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "_(no rows)_\n"
    columns = frame.columns
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in frame.iter_rows(named=True):
        cells = []
        for column in columns:
            value = row[column]
            if isinstance(value, float):
                cells.append(f"{value:.4f}")
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def write_summary_markdown(
    out_dir: Path,
    metadata: dict[str, Any],
    correlations: pl.DataFrame,
    deviation_summary: dict[str, Any],
    outlier_summary: dict[str, Any],
    tiers: dict[str, list[dict[str, object]]],
) -> None:
    counts = metadata["counts"]
    lines: list[str] = []
    lines.append("# Bacterial resistance analysis")
    lines.append("")
    lines.append(f"Source: `{metadata['source']}`")
    lines.append(
        f"Date range: {metadata['date_range']['start']} to {metadata['date_range']['end']}"
    )
    lines.append("")
    lines.append("## Dataset")
    lines.append("")
    lines.append(f"- patients: {counts['patients']}")
    lines.append(f"- cultures: {counts['cultures']}")
    lines.append(f"- isolates: {counts['isolates']}")
    lines.append(f"- susceptibility results: {counts['susceptibility_results']}")
    lines.append("")
    lines.append("## Deviations (logged only, no data changed)")
    lines.append("")
    lines.append(f"- total detected: {deviation_summary['total']}")
    lines.append(f"- by family: {deviation_summary['by_family']}")
    lines.append(f"- by detector: {deviation_summary['by_detector']}")
    lines.append("")
    lines.append("## Outliers (95% funnel, reference = ward_type)")
    lines.append("")
    lines.append(f"- total detected: {outlier_summary['total']}")
    lines.append(f"- by detector: {outlier_summary['by_detector']}")
    lines.append("")
    lines.append("## Strongest correlations (by Cramer's V)")
    lines.append("")
    lines.append(_markdown_table(_top_correlations(correlations)).rstrip("\n"))
    lines.append("")
    lines.append("## Example antibiotic tier list (Escherichia coli | urine)")
    lines.append("")
    example = tiers.get("Escherichia coli|urine", [])[:6]
    if example:
        lines.append(_markdown_table(pl.DataFrame(example)).rstrip("\n"))
    else:
        lines.append("_(no tier list available)_")
    lines.append("")
    lines.append("## Caveats")
    lines.append("")
    lines.append("- Data is synthetic (seed 2026).")
    lines.append("- VRE (5) and CPE (12) positives are too few for stable rates.")
    lines.append(
        "- Flag rates are per organism and use the marker antibiotic denominator "
        "present in susceptibility.csv."
    )
    lines.append(
        "- Surveillance rule applied: first isolate per patient x species x specimen."
    )
    lines.append(
        "- Outliers are 95% funnel deviations from the same-ward_type reference; "
        "no multiple-comparison control is applied, so ~5% of cells fall outside "
        "by chance."
    )
    lines.append(
        "- Weekly outlier cells are only compared where the organism/agent/specimen "
        f"strand has >= {TEMPORAL_REPORTING_FLOOR} results."
    )
    lines.append("")
    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
