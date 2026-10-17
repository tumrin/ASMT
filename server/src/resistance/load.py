from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl
from polars.datatypes import DataTypeClass


class SchemaError(ValueError):
    """Raised when an input file is missing, malformed or has drifted."""


SCHEMAS: dict[str, dict[str, DataTypeClass]] = {
    "patients.csv": {
        "patient_id": pl.String,
        "sex": pl.String,
        "birth_year": pl.Int32,
        "home_area": pl.String,
    },
    "cultures.csv": {
        "culture_id": pl.String,
        "patient_id": pl.String,
        "age_years": pl.Int32,
        "sample_date": pl.String,
        "iso_year": pl.Int32,
        "iso_week": pl.Int32,
        "ward_code": pl.String,
        "ward_fi": pl.String,
        "ward_en": pl.String,
        "ward_type": pl.String,
        "institution": pl.String,
        "admission_date": pl.String,
        "specimen": pl.String,
        "specimen_fi": pl.String,
        "result": pl.String,
        "n_isolates": pl.Int32,
    },
    "isolates.csv": {
        "isolate_id": pl.String,
        "culture_id": pl.String,
        "isolate_no": pl.Int32,
        "organism": pl.String,
        "quantity": pl.String,
        "esbl": pl.Int8,
        "mrsa": pl.Int8,
        "vre": pl.Int8,
        "cpe": pl.Int8,
    },
    "susceptibility.csv": {
        "isolate_id": pl.String,
        "culture_id": pl.String,
        "organism": pl.String,
        "antibiotic": pl.String,
        "antibiotic_code": pl.String,
        "antibiotic_fi": pl.String,
        "result": pl.String,
        "guideline": pl.String,
    },
    "antibiotics.csv": {
        "antibiotic": pl.String,
        "antibiotic_code": pl.String,
        "antibiotic_fi": pl.String,
        "class": pl.String,
        "reported_for": pl.String,
    },
    "wards.csv": {
        "ward_code": pl.String,
        "ward_fi": pl.String,
        "ward_en": pl.String,
        "ward_type": pl.String,
        "institution": pl.String,
    },
}


@dataclass
class Dataset:
    patients: pl.DataFrame
    cultures: pl.DataFrame
    isolates: pl.DataFrame
    susceptibility: pl.DataFrame
    antibiotics: pl.DataFrame
    wards: pl.DataFrame


def read_table(path: Path, schema: dict[str, DataTypeClass]) -> pl.DataFrame:
    if not path.exists():
        raise SchemaError(f"missing file: {path}")
    df = pl.read_csv(path, schema_overrides=schema, null_values=[""])
    missing = [c for c in schema if c not in df.columns]
    if missing:
        raise SchemaError(f"{path.name}: missing columns {missing}")
    extra = [c for c in df.columns if c not in schema]
    if extra:
        raise SchemaError(f"{path.name}: unexpected columns {extra}")
    return df.select(list(schema))


def normalize_organism(column: str = "organism") -> pl.Expr:
    """Trim, lowercase, and collapse each run of dots/whitespace into one `_`."""
    return (
        pl.col(column)
        .str.strip_chars()
        .str.to_lowercase()
        .str.replace_all(r"[.\s]+", "_")
    )


def load_dataset(data_dir: Path) -> Dataset:
    frames = {
        name: read_table(data_dir / name, schema) for name, schema in SCHEMAS.items()
    }
    ds = Dataset(
        patients=frames["patients.csv"],
        cultures=frames["cultures.csv"],
        isolates=frames["isolates.csv"].with_columns(normalize_organism()),
        susceptibility=frames["susceptibility.csv"].with_columns(normalize_organism()),
        antibiotics=frames["antibiotics.csv"],
        wards=frames["wards.csv"],
    )
    for name, df, key in (
        ("patients", ds.patients, "patient_id"),
        ("cultures", ds.cultures, "culture_id"),
        ("isolates", ds.isolates, "isolate_id"),
    ):
        if df[key].n_unique() != df.height:
            raise SchemaError(f"{name}: duplicate {key}")
    return ds
