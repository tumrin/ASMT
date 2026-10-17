from __future__ import annotations

from collections import defaultdict
from typing import Any

import polars as pl
from resistance_core.antibiotic_properties import metadata_from_row

from .config import Settings
from .load import Dataset


def _susceptibility_map(ab_analytics: pl.DataFrame) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for isolate_id, antibiotic, outcome in ab_analytics.select(
        "isolate_id", "antibiotic", "result"
    ).iter_rows():
        result.setdefault(isolate_id, {})[antibiotic] = outcome
    return result


def _isolate_records(
    analytics: pl.DataFrame, susceptibility: dict[str, dict[str, str]]
) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    for row in analytics.select(
        "isolate_id",
        "culture_id",
        "isolate_no",
        "organism",
        "quantity",
        "esbl",
        "mrsa",
        "vre",
        "cpe",
        "n_resistant_classes",
    ).iter_rows(named=True):
        records[row["isolate_id"]] = {
            "isolate_id": row["isolate_id"],
            "isolate_no": row["isolate_no"],
            "organism": row["organism"],
            "quantity": row["quantity"],
            "flags": {
                "esbl": int(row["esbl"]),
                "mrsa": int(row["mrsa"]),
                "vre": int(row["vre"]),
                "cpe": int(row["cpe"]),
            },
            "n_resistant_classes": int(row["n_resistant_classes"]),
            "susceptibility": susceptibility.get(row["isolate_id"], {}),
        }
    return records


def _antibiotic_payload(row: dict[str, Any]) -> dict[str, Any]:
    meta = metadata_from_row(row)
    return {
        "antibiotic": meta.antibiotic,
        "antibiotic_code": meta.antibiotic_code,
        "antibiotic_fi": row.get("antibiotic_fi"),
        "class": meta.antibiotic_class,
        "reported_for": meta.reported_for,
        "role": meta.role,
        "marker_flags": list(meta.marker_flags),
    }


def build_document(
    ds: Dataset,
    contexts: pl.DataFrame,
    analytics: pl.DataFrame,
    ab_analytics: pl.DataFrame,
    tiers: dict[str, list[dict[str, object]]],
    ward_summaries: dict[str, dict[str, Any]],
    deviation_summary: dict[str, Any],
    outlier_summary: dict[str, Any],
    settings: Settings,
    age_band_edges: tuple[float, ...],
) -> dict[str, Any]:
    susceptibility = _susceptibility_map(ab_analytics)
    isolates = _isolate_records(analytics, susceptibility)

    isolates_by_culture: dict[str, list[dict[str, object]]] = defaultdict(list)
    isolate_culture = analytics.select("isolate_id", "culture_id")
    for isolate_id, culture_id in isolate_culture.iter_rows():
        record = isolates.get(isolate_id)
        if record is not None:
            isolates_by_culture[culture_id].append(record)

    patients_meta = {
        row["patient_id"]: row for row in ds.patients.iter_rows(named=True)
    }
    wards_meta = {row["ward_code"]: row for row in ds.wards.iter_rows(named=True)}

    patients: dict[str, dict[str, Any]] = {}

    context_rows = contexts.sort("patient_id", "ward_code", "sample_date")
    for row in context_rows.iter_rows(named=True):
        patient_id = row["patient_id"]
        ward_code = row["ward_code"]
        meta = patients_meta.get(patient_id, {})
        patient = patients.setdefault(
            patient_id,
            {
                "patient_id": patient_id,
                "sex": meta.get("sex"),
                "birth_year": meta.get("birth_year"),
                "home_area": meta.get("home_area"),
                "wards": {},
            },
        )
        ward_meta = wards_meta.get(ward_code, {})
        ward = patient["wards"].setdefault(
            ward_code,
            {
                "ward_code": ward_code,
                "ward_fi": ward_meta.get("ward_fi"),
                "ward_en": ward_meta.get("ward_en"),
                "ward_type": ward_meta.get("ward_type"),
                "institution": ward_meta.get("institution"),
                "cultures": [],
            },
        )
        ward["cultures"].append(
            {
                "culture_id": row["culture_id"],
                "sample_date": str(row["sample_date"]),
                "iso_year": row["iso_year"],
                "iso_week": row["iso_week"],
                "age_years": row["age_years"],
                "specimen": row["specimen"],
                "result": row["result"],
                "n_isolates": row["n_isolates"],
                "days_since_admission": row["days_since_admission"],
                "isolates": isolates_by_culture.get(row["culture_id"], []),
            }
        )

    sample_dates = contexts["sample_date"]

    for patient_id, meta in patients_meta.items():
        patients.setdefault(
            patient_id,
            {
                "patient_id": patient_id,
                "sex": meta.get("sex"),
                "birth_year": meta.get("birth_year"),
                "home_area": meta.get("home_area"),
                "wards": {},
            },
        )

    metadata = {
        "source": str(settings.data_dir),
        "counts": {
            "patients": ds.patients.height,
            "cultures": ds.cultures.height,
            "isolates": ds.isolates.height,
            "susceptibility_results": ds.susceptibility.height,
        },
        "date_range": {
            "start": str(sample_dates.min()),
            "end": str(sample_dates.max()),
        },
        "as_of": str(sample_dates.max()),
        "age_band_edges": list(age_band_edges),
        "settings": settings.to_json(),
        "deviation_summary": deviation_summary,
        "outlier_summary": outlier_summary,
    }

    return {
        "metadata": metadata,
        "antibiotics": [
            _antibiotic_payload(row) for row in ds.antibiotics.iter_rows(named=True)
        ],
        "wards": ward_summaries,
        "patients": patients,
        "antibiotic_tiers": tiers,
    }
