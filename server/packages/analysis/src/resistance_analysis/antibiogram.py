from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import polars as pl
from resistance_core.antibiotic_properties import metadata_by_code

from .config import Settings

LAST4W = "last4w"
LAST4W_DAYS = 28

# Inpatient sub-scopes by onset (spec §6.2): a culture is hospital-onset at or after
# `Settings.hospital_onset_days` days since admission, community-onset before that.
WARD_EARLY = "ward-early"
WARD_LATE = "ward-late"


@dataclass
class Antibiogram:
    matrix: dict[str, dict[str, list[dict[str, Any]]]]
    scopes: dict[str, list[dict[str, str]]]
    periods: list[str]
    data_as_of: date | None


def _annual_windows(isolates: pl.DataFrame) -> dict[str, tuple[date, date]]:
    years = sorted(isolates["sample_date"].dt.year().unique().to_list())
    return {f"annual:{year}": (date(year, 1, 1), date(year, 12, 31)) for year in years}


def _period_windows(
    isolates: pl.DataFrame, data_as_of: date
) -> dict[str, tuple[date, date]]:
    windows = _annual_windows(isolates)
    windows[LAST4W] = (data_as_of - timedelta(days=LAST4W_DAYS - 1), data_as_of)
    return windows


def _first_isolates(
    isolates: pl.DataFrame,
    windows: dict[str, tuple[date, date]],
) -> pl.DataFrame:
    """First isolate per patient x organism x specimen x setting per period.

    Splitting by ``ward_type`` keeps inpatient (ward) and outpatient (region) scopes
    independent: a patient seen in both settings contributes one first isolate to each
    instead of one setting suppressing the other. ``is_global_first`` marks the earliest
    isolate across settings, which the hospital scope counts (spec §6.1).
    """
    frames: list[pl.DataFrame] = []
    for label, (start, end) in windows.items():
        window = isolates.filter(
            (pl.col("sample_date") >= start) & (pl.col("sample_date") <= end)
        ).sort("sample_date", "isolate_id")
        setting_first = window.group_by(
            "patient_id", "organism", "specimen", "ward_type", maintain_order=True
        ).agg(pl.col("isolate_id").first().alias("isolate_id"))
        global_first = window.group_by(
            "patient_id", "organism", "specimen", maintain_order=True
        ).agg(pl.col("isolate_id").first().alias("isolate_id"))
        frames.append(
            setting_first.select("isolate_id").with_columns(
                pl.col("isolate_id")
                .is_in(global_first["isolate_id"].to_list())
                .alias("is_global_first"),
                pl.lit(label).alias("period"),
            )
        )
    if not frames:
        return pl.DataFrame(
            schema={
                "isolate_id": pl.String,
                "is_global_first": pl.Boolean,
                "period": pl.String,
            }
        )
    return pl.concat(frames)


def _max_date(frame: pl.DataFrame) -> date:
    value = frame["sample_date"].max()
    if not isinstance(value, date):
        raise TypeError("sample_date must be a date column")
    return value


def _traffic_light(rate: float, settings: Settings) -> str:
    if rate > settings.green_above:
        return "green"
    if rate > settings.yellow_above:
        return "yellow"
    return "red"


def _entry(row: dict[str, Any], role: str, settings: Settings) -> dict[str, Any]:
    n = int(row["n"])
    n_s = int(row["n_s"])
    if n >= settings.min_isolates:
        rate = n_s / n
        return {
            "antibiotic": row["antibiotic"],
            "antibiotic_code": row["antibiotic_code"],
            "class": row["class"],
            "reported_for": row["reported_for"],
            "role": role,
            "n": n,
            "n_s": n_s,
            "susceptibility_rate": round(rate, 4),
            "traffic_light": _traffic_light(rate, settings),
        }
    return {
        "antibiotic": row["antibiotic"],
        "antibiotic_code": row["antibiotic_code"],
        "class": row["class"],
        "reported_for": row["reported_for"],
        "role": role,
        "n": n,
        "n_s": n_s,
        "susceptibility_rate": None,
        "traffic_light": "none",
    }


def _scoped_rows(rows: pl.DataFrame, settings: Settings) -> pl.DataFrame:
    # Ward and region count the first isolate per setting; hospital keeps the global
    # first isolate across settings (spec §6.1).
    hospital = rows.filter(pl.col("is_global_first")).with_columns(
        pl.lit("hospital").alias("scope"), pl.lit("-").alias("unit")
    )
    inpatients = rows.filter(pl.col("ward_type") == "in")
    ward = inpatients.with_columns(
        pl.lit("ward").alias("scope"), pl.col("ward_code").alias("unit")
    )
    # Onset sub-scopes partition the inpatient first isolates, so a fresh admission and
    # a long stay track their own data. The rates follow the data automatically: if
    # community-onset cultures drift toward community resistance, ward-early drifts with
    # them. Cultures without an admission date stay in ward only.
    days = pl.col("days_since_admission")
    early = inpatients.filter(
        days.is_not_null() & (days < settings.hospital_onset_days)
    ).with_columns(pl.lit(WARD_EARLY).alias("scope"), pl.col("ward_code").alias("unit"))
    late = inpatients.filter(
        days.is_not_null() & (days >= settings.hospital_onset_days)
    ).with_columns(pl.lit(WARD_LATE).alias("scope"), pl.col("ward_code").alias("unit"))
    region = rows.filter(pl.col("ward_type") == "out").with_columns(
        pl.lit("region").alias("scope"), pl.col("home_area").alias("unit")
    )
    return pl.concat([hospital, ward, early, late, region])


def _scopes(
    contexts: pl.DataFrame, patients: pl.DataFrame, wards: pl.DataFrame
) -> dict[str, list[dict[str, str]]]:
    in_wards = [
        {
            "unit": row["ward_code"],
            "label": row.get("ward_en") or row.get("ward_fi") or row["ward_code"],
        }
        for row in wards.filter(pl.col("ward_type") == "in")
        .sort("ward_code")
        .iter_rows(named=True)
    ]
    out = (
        contexts.filter(pl.col("ward_type") == "out")
        .select("patient_id")
        .join(patients.select("patient_id", "home_area"), on="patient_id", how="left")
    )
    regions = [
        {"unit": area, "label": area}
        for area in sorted(out["home_area"].drop_nulls().unique().to_list())
    ]
    return {
        "hospital": [{"unit": "-", "label": "Hospital"}],
        "ward": in_wards,
        "ward-early": in_wards,
        "ward-late": in_wards,
        "region": regions,
    }


def build_antibiogram(
    contexts: pl.DataFrame,
    isolates: pl.DataFrame,
    ab_analytics: pl.DataFrame,
    patients: pl.DataFrame,
    wards: pl.DataFrame,
    antibiotics: pl.DataFrame,
    settings: Settings,
) -> Antibiogram:
    """Build the scope x period x (organism, specimen) susceptibility matrix."""
    scopes = _scopes(contexts, patients, wards)
    data_as_of = None if contexts.is_empty() else _max_date(contexts)
    if isolates.is_empty() or ab_analytics.is_empty() or data_as_of is None:
        return Antibiogram({}, scopes, [], data_as_of)

    windows = _period_windows(isolates, data_as_of)
    first = _first_isolates(isolates, windows)

    rows = (
        ab_analytics.join(first, on="isolate_id", how="inner")
        .filter(
            (pl.col("reported_for") == "all")
            | (pl.col("reported_for") == pl.col("specimen"))
        )
        .pipe(_scoped_rows, settings)
    )

    grouping = [
        "scope",
        "unit",
        "period",
        "organism",
        "specimen",
        "antibiotic",
        "antibiotic_code",
        "class",
        "reported_for",
    ]
    aggregated = rows.group_by(grouping).agg(
        pl.len().alias("n"), pl.col("is_s").sum().alias("n_s")
    )

    metadata = metadata_by_code(antibiotics)
    matrix: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in aggregated.iter_rows(named=True):
        meta = metadata.get(row["antibiotic_code"])
        role = meta.role if meta is not None else "therapeutic"
        key = f"{row['scope']}|{row['unit']}|{row['period']}"
        organism_key = f"{row['organism']}|{row['specimen']}"
        matrix.setdefault(key, {}).setdefault(organism_key, []).append(
            _entry(row, role, settings)
        )
    for organisms in matrix.values():
        for entries in organisms.values():
            entries.sort(key=lambda entry: entry["antibiotic"])

    periods = [label for label in windows if label != LAST4W] + [LAST4W]
    return Antibiogram(
        matrix=matrix,
        scopes=scopes,
        periods=periods,
        data_as_of=data_as_of,
    )
