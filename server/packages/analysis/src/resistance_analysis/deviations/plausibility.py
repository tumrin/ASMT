from __future__ import annotations

import re

import polars as pl

from ..load import Dataset
from .models import (
    UNIT_CULTURE,
    UNIT_ISOLATE,
    UNIT_SUSCEPTIBILITY,
    Deviation,
    Family,
    Severity,
    make_deviation,
)

# `result` and `guideline` are the only fields with a declared value shape in
# the dataset README ("EUCAST + year"), so they are checked as a grammar rather
# than against a curated list. Every other rule below is read from the data.
RESULT_VALUES = ("positive", "negative", "mixed_growth")
GUIDELINE_PATTERN = r"^EUCAST \d{4}$"
QUANTITY_NUMERIC = re.compile(r"^(>=)?10\^\d+$")
QUANTITY_PLUS = re.compile(r"^\+{1,3}$")


def _dev(
    detector: str,
    unit_type: str,
    unit_key: str,
    metric: str,
    expected: str,
    observed: str,
    threshold: str,
    severity: Severity,
    **detail: object,
) -> Deviation:
    """Plausibility deviations are logged, never applied to the data."""
    return make_deviation(
        Family.CONSISTENCY,
        detector,
        unit_type,
        unit_key,
        metric,
        expected,
        observed,
        threshold,
        severity,
        **detail,
    )


def _duplicate_susceptibility_keys(ds: Dataset) -> list[Deviation]:
    duplicates = (
        ds.susceptibility.group_by("isolate_id", "antibiotic_code")
        .len()
        .filter(pl.col("len") > 1)
        .sort("isolate_id", "antibiotic_code")
    )
    return [
        _dev(
            "duplicate_susceptibility_key",
            UNIT_SUSCEPTIBILITY,
            f"{row['isolate_id']}:{row['antibiotic_code']}",
            "antibiotic_code",
            "isolate x antibiotic appears once",
            f"{row['len']} rows",
            "count == 1",
            Severity.CRITICAL,
            isolate_id=row["isolate_id"],
            antibiotic_code=row["antibiotic_code"],
            count=int(row["len"]),
        )
        for row in duplicates.iter_rows(named=True)
    ]


def _week_year_mismatches(cultures: pl.DataFrame) -> list[Deviation]:
    parsed = cultures.with_columns(pl.col("sample_date").str.to_date().alias("_date"))
    offenders = parsed.filter(
        (pl.col("_date").dt.iso_year() != pl.col("iso_year"))
        | (pl.col("_date").dt.week() != pl.col("iso_week"))
    )
    return [
        _dev(
            "week_year_mismatch",
            UNIT_CULTURE,
            row["culture_id"],
            "iso_year/iso_week",
            "ISO year and week of sample_date",
            f"{row['iso_year']}-W{row['iso_week']}",
            "matches sample_date",
            Severity.WARNING,
            culture_id=row["culture_id"],
            sample_date=str(row["sample_date"]),
        )
        for row in offenders.iter_rows(named=True)
    ]


def _age_birth_year_mismatches(ds: Dataset) -> list[Deviation]:
    """`age_years` must match the sample year minus the birth year.

    A one-year difference is allowed because the birthday is unknown.
    """
    joined = cultures_with_patients(ds).filter(pl.col("birth_year").is_not_null())
    offenders = joined.filter(
        (pl.col("age_years") - (pl.col("_year") - pl.col("birth_year"))).abs() > 1
    )
    return [
        _dev(
            "age_birth_year_mismatch",
            UNIT_CULTURE,
            row["culture_id"],
            "age_years",
            "sample year minus birth year",
            f"age_years={row['age_years']}, implied {row['_year'] - row['birth_year']}",
            "difference <= 1",
            Severity.WARNING,
            culture_id=row["culture_id"],
            age_years=row["age_years"],
            birth_year=row["birth_year"],
        )
        for row in offenders.iter_rows(named=True)
    ]


def _admission_after_sample(ds: Dataset) -> list[Deviation]:
    parsed = cultures_with_dates(ds)
    offenders = parsed.filter(
        pl.col("_admission").is_not_null() & (pl.col("_admission") > pl.col("_date"))
    )
    return [
        _dev(
            "admission_after_sample",
            UNIT_CULTURE,
            row["culture_id"],
            "admission_date",
            "admission on or before sample_date",
            f"{row['admission_date']} after {row['sample_date']}",
            "admission_date <= sample_date",
            Severity.CRITICAL,
            culture_id=row["culture_id"],
            admission_date=str(row["admission_date"]),
            sample_date=str(row["sample_date"]),
        )
        for row in offenders.iter_rows(named=True)
    ]


def _admission_date_presence(ds: Dataset) -> list[Deviation]:
    parsed = cultures_with_dates(ds)
    offenders = parsed.filter(
        ((pl.col("ward_type") == "in") & pl.col("_admission").is_null())
        | ((pl.col("ward_type") == "out") & pl.col("_admission").is_not_null())
    )
    return [
        _dev(
            "admission_date_presence",
            UNIT_CULTURE,
            row["culture_id"],
            "admission_date",
            "inpatients have an admission_date, outpatients do not",
            f"ward_type={row['ward_type']}, admission_date="
            f"{'set' if row['_admission'] is not None else 'null'}",
            "presence matches ward_type",
            Severity.WARNING,
            culture_id=row["culture_id"],
            ward_type=row["ward_type"],
        )
        for row in offenders.iter_rows(named=True)
    ]


def _culture_ward_metadata_mismatches(ds: Dataset) -> list[Deviation]:
    columns = ("ward_fi", "ward_en", "ward_type", "institution")
    joined = ds.cultures.select("culture_id", "ward_code", *columns).join(
        ds.wards.select("ward_code", *columns),
        on="ward_code",
        how="left",
        suffix="_ref",
    )
    deviations: list[Deviation] = []
    for row in joined.iter_rows(named=True):
        if row["ward_fi_ref"] is None:
            differing = ["ward_code"]
        else:
            differing = [c for c in columns if row[c] != row[f"{c}_ref"]]
        if not differing:
            continue
        deviations.append(
            _dev(
                "culture_ward_metadata_mismatch",
                UNIT_CULTURE,
                row["culture_id"],
                "ward metadata",
                "culture ward fields equal wards.csv",
                f"{', '.join(differing)} differ",
                "ward fields match wards.csv",
                Severity.WARNING,
                culture_id=row["culture_id"],
                ward_code=row["ward_code"],
                fields=differing,
            )
        )
    return deviations


def _specimen_label_mismatches(ds: Dataset) -> list[Deviation]:
    canonical = (
        ds.cultures.group_by("specimen", "specimen_fi")
        .len()
        .sort("len", "specimen_fi", descending=[True, False])
        .group_by("specimen")
        .agg(pl.col("specimen_fi").first().alias("_canonical"))
    )
    joined = ds.cultures.select("culture_id", "specimen", "specimen_fi").join(
        canonical, on="specimen", how="left"
    )
    offenders = joined.filter(pl.col("specimen_fi") != pl.col("_canonical"))
    return [
        _dev(
            "specimen_label_mismatch",
            UNIT_CULTURE,
            row["culture_id"],
            "specimen_fi",
            f"'{row['specimen']}' labels as '{row['_canonical']}'",
            f"specimen_fi='{row['specimen_fi']}'",
            "specimen_fi == the observed label for the specimen",
            Severity.WARNING,
            culture_id=row["culture_id"],
            specimen=row["specimen"],
            specimen_fi=row["specimen_fi"],
        )
        for row in offenders.iter_rows(named=True)
    ]


def _quantity_shape(value: str | None) -> str:
    if value is None:
        return "none"
    if QUANTITY_NUMERIC.match(value):
        return "numeric"
    if QUANTITY_PLUS.match(value):
        return "plus"
    return "unknown"


def _quantity_format_invalid(ds: Dataset) -> list[Deviation]:
    """A quantity must match the shape its specimen uses in this dataset."""
    paired = ds.isolates.select("isolate_id", "culture_id", "quantity").join(
        ds.cultures.select("culture_id", "specimen"), on="culture_id", how="left"
    )
    shapes = [
        {"specimen": row["specimen"], "shape": _quantity_shape(row["quantity"])}
        for row in paired.iter_rows(named=True)
    ]
    counts: dict[str, dict[str, int]] = {}
    for entry in shapes:
        bucket = counts.setdefault(entry["specimen"] or "", {})
        bucket[entry["shape"]] = bucket.get(entry["shape"], 0) + 1
    dominant = {
        specimen: min(bucket.items(), key=lambda item: (-item[1], item[0]))[0]
        for specimen, bucket in counts.items()
    }
    deviations: list[Deviation] = []
    for row, entry in zip(paired.iter_rows(named=True), shapes, strict=True):
        shape = entry["shape"]
        expected = dominant.get(row["specimen"] or "", "unknown")
        if shape == expected:
            continue
        deviations.append(
            _dev(
                "quantity_format_invalid",
                UNIT_ISOLATE,
                row["isolate_id"],
                "quantity",
                f"'{row['specimen']}' quantities have shape '{expected}'",
                f"quantity='{row['quantity']}' (shape '{shape}')",
                "shape matches the specimen",
                Severity.WARNING,
                isolate_id=row["isolate_id"],
                specimen=row["specimen"],
                quantity=row["quantity"],
            )
        )
    return deviations


def _unknown_result_values(ds: Dataset) -> list[Deviation]:
    offenders = ds.cultures.filter(~pl.col("result").is_in(RESULT_VALUES))
    return [
        _dev(
            "unknown_result_value",
            UNIT_CULTURE,
            row["culture_id"],
            "result",
            f"one of {RESULT_VALUES}",
            f"result='{row['result']}'",
            "result in the declared set",
            Severity.CRITICAL,
            culture_id=row["culture_id"],
            result=row["result"],
        )
        for row in offenders.iter_rows(named=True)
    ]


def _duplicate_isolate_numbers(ds: Dataset) -> list[Deviation]:
    duplicates = (
        ds.isolates.group_by("culture_id", "isolate_no")
        .len()
        .filter(pl.col("len") > 1)
        .sort("culture_id", "isolate_no")
    )
    return [
        _dev(
            "duplicate_isolate_no",
            UNIT_CULTURE,
            row["culture_id"],
            "isolate_no",
            "isolate_no unique within a culture",
            f"isolate_no {row['isolate_no']} appears {row['len']} times",
            "count == 1",
            Severity.WARNING,
            culture_id=row["culture_id"],
            isolate_no=row["isolate_no"],
            count=int(row["len"]),
        )
        for row in duplicates.iter_rows(named=True)
    ]


def _susceptibility_organism_mismatches(ds: Dataset) -> list[Deviation]:
    joined = ds.susceptibility.join(
        ds.isolates.select("isolate_id", pl.col("organism").alias("_isolate_organism")),
        on="isolate_id",
        how="left",
    )
    offenders = joined.filter(
        pl.col("_isolate_organism").is_not_null()
        & (pl.col("organism") != pl.col("_isolate_organism"))
    )
    return [
        _dev(
            "susceptibility_organism_mismatch",
            UNIT_SUSCEPTIBILITY,
            f"{row['isolate_id']}:{row['antibiotic_code']}",
            "organism",
            "susceptibility organism equals the isolate organism",
            f"'{row['organism']}' vs '{row['_isolate_organism']}'",
            "organisms equal",
            Severity.CRITICAL,
            isolate_id=row["isolate_id"],
            organism=row["organism"],
        )
        for row in offenders.iter_rows(named=True)
    ]


def _unknown_guidelines(ds: Dataset) -> list[Deviation]:
    valid = pl.col("guideline").str.contains(GUIDELINE_PATTERN)
    offenders = ds.susceptibility.filter(pl.col("guideline").is_null() | valid.not_())
    return [
        _dev(
            "unknown_guideline",
            UNIT_SUSCEPTIBILITY,
            f"{row['isolate_id']}:{row['antibiotic_code']}",
            "guideline",
            "EUCAST + year",
            f"guideline='{row['guideline']}'",
            "matches ^EUCAST \\d{4}$",
            Severity.WARNING,
            isolate_id=row["isolate_id"],
            guideline=row["guideline"],
        )
        for row in offenders.iter_rows(named=True)
    ]


def cultures_with_dates(ds: Dataset) -> pl.DataFrame:
    return ds.cultures.with_columns(
        pl.col("sample_date").str.to_date().alias("_date"),
        pl.col("admission_date").str.to_date().alias("_admission"),
    )


def cultures_with_patients(ds: Dataset) -> pl.DataFrame:
    return (
        ds.cultures.with_columns(
            pl.col("sample_date").str.to_date().alias("_date"),
        )
        .with_columns(pl.col("_date").dt.year().alias("_year"))
        .join(
            ds.patients.select("patient_id", "birth_year"),
            on="patient_id",
            how="left",
        )
    )


def detect(ds: Dataset) -> list[Deviation]:
    """Field-level and cross-table plausibility checks. Nothing is removed."""
    return [
        *_duplicate_susceptibility_keys(ds),
        *_week_year_mismatches(ds.cultures),
        *_age_birth_year_mismatches(ds),
        *_admission_after_sample(ds),
        *_admission_date_presence(ds),
        *_culture_ward_metadata_mismatches(ds),
        *_specimen_label_mismatches(ds),
        *_quantity_format_invalid(ds),
        *_unknown_result_values(ds),
        *_duplicate_isolate_numbers(ds),
        *_susceptibility_organism_mismatches(ds),
        *_unknown_guidelines(ds),
    ]
