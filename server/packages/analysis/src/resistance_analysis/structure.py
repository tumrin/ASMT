from __future__ import annotations

from collections import defaultdict
from typing import Any

import polars as pl
from resistance_core.antibiotic_properties import metadata_from_row

from .antibiogram import Antibiogram
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
    }


def _ward_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "ward_code": row.get("ward_code"),
        "ward_fi": row.get("ward_fi"),
        "ward_en": row.get("ward_en"),
        "ward_type": row.get("ward_type"),
        "institution": row.get("institution"),
    }


def _patient_payload(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "patient_id": meta.get("patient_id"),
        "sex": meta.get("sex"),
        "birth_year": meta.get("birth_year"),
        "home_area": meta.get("home_area"),
        "wards": {},
    }


def build_document(
    ds: Dataset,
    contexts: pl.DataFrame,
    analytics: pl.DataFrame,
    ab_analytics: pl.DataFrame,
    antibiogram: Antibiogram,
    settings: Settings,
) -> dict[str, Any]:
    susceptibility = _susceptibility_map(ab_analytics)
    isolates = _isolate_records(analytics, susceptibility)

    isolates_by_culture: dict[str, list[dict[str, object]]] = defaultdict(list)
    for isolate_id, culture_id in analytics.select(
        "isolate_id", "culture_id"
    ).iter_rows():
        record = isolates.get(isolate_id)
        if record is not None:
            isolates_by_culture[culture_id].append(record)

    patients_meta = {
        row["patient_id"]: row for row in ds.patients.iter_rows(named=True)
    }
    wards_meta = {row["ward_code"]: row for row in ds.wards.iter_rows(named=True)}

    patients: dict[str, dict[str, Any]] = {
        patient_id: _patient_payload(meta) for patient_id, meta in patients_meta.items()
    }

    context_rows = contexts.sort("patient_id", "ward_code", "sample_date")
    for row in context_rows.iter_rows(named=True):
        patient = patients.get(row["patient_id"])
        if patient is None:
            patient = _patient_payload({"patient_id": row["patient_id"]})
            patients[row["patient_id"]] = patient
        ward_meta = wards_meta.get(row["ward_code"], {})
        ward = patient["wards"].setdefault(
            row["ward_code"],
            {
                **_ward_payload(ward_meta),
                "ward_code": row["ward_code"],
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
        "data_as_of": str(sample_dates.max()),
        "settings": settings.to_json(),
        "scopes": antibiogram.scopes,
        "periods": antibiogram.periods,
    }

    return {
        "metadata": metadata,
        "antibiotics": [
            _antibiotic_payload(row) for row in ds.antibiotics.iter_rows(named=True)
        ],
        "wards": {code: _ward_payload(meta) for code, meta in wards_meta.items()},
        "patients": patients,
        "antibiogram": antibiogram.matrix,
    }
