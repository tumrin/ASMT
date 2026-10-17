from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from resistance.load import SchemaError, load_dataset
from tests.conftest import write_dataset


def test_load_dataset_roundtrip(dataset_dir: Path) -> None:
    ds = load_dataset(dataset_dir)
    assert ds.patients.height == 4
    assert ds.cultures.height == 5
    assert ds.isolates.height == 4
    assert ds.susceptibility.height == 7


def test_load_reads_empty_admission_date_as_null(dataset_dir: Path) -> None:
    ds = load_dataset(dataset_dir)
    assert ds.cultures.filter(pl.col("culture_id") == "C2")["admission_date"][0] is None


def test_missing_column_raises(tmp_path: Path) -> None:
    directory = write_dataset(tmp_path / "data")
    (directory / "patients.csv").write_text("patient_id,sex\nP1,F\n", encoding="utf-8")
    with pytest.raises(SchemaError):
        load_dataset(directory)


def test_unexpected_column_raises(tmp_path: Path) -> None:
    directory = write_dataset(tmp_path / "data")
    (directory / "wards.csv").write_text(
        "ward_code,ward_fi,ward_en,ward_type,institution,surprise\n"
        "MED-A,Sisätaudit A,Internal medicine A,in,hospital,x\n",
        encoding="utf-8",
    )
    with pytest.raises(SchemaError):
        load_dataset(directory)
