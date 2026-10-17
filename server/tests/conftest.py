from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import polars as pl
import pytest
from resistance_analysis.config import Settings
from resistance_analysis.load import SCHEMAS


def small_frames() -> dict[str, pl.DataFrame]:
    """A tiny dataset with deliberately injected anomalies.

    Anomalies: C5-1 is MRSA on E. coli, C2-1 is MRSA but cefoxitin S, C2-1 has a
    urine-only agent on a blood specimen, and negative culture C4 carries an isolate.
    """
    patients = pl.DataFrame(
        {
            "patient_id": ["P1", "P2", "P3", "P4"],
            "sex": ["F", "M", "F", "M"],
            "birth_year": [1990, 1950, 2000, 1975],
            "home_area": ["Centre", "East", "Centre", "West"],
        },
        schema=SCHEMAS["patients.csv"],
    )
    cultures = pl.DataFrame(
        {
            "culture_id": ["C1", "C2", "C3", "C4", "C5"],
            "patient_id": ["P1", "P2", "P3", "P4", "P1"],
            "age_years": [34, 74, 24, 49, 34],
            "sample_date": [
                "2024-01-01",
                "2024-01-02",
                "2024-01-03",
                "2024-01-04",
                "2024-01-05",
            ],
            "iso_year": [2024, 2024, 2024, 2024, 2024],
            "iso_week": [1, 1, 1, 1, 1],
            "ward_code": ["MED-A", "ICU", "PHC-N", "MED-B", "MED-A"],
            "ward_fi": [
                "Sisätaudit A",
                "Teho-osasto",
                "Terveysasema Pohjoinen",
                "Sisätaudit B",
                "Sisätaudit A",
            ],
            "ward_en": [
                "Internal medicine A",
                "Intensive care unit",
                "Health centre North",
                "Internal medicine B",
                "Internal medicine A",
            ],
            "ward_type": ["in", "in", "out", "in", "in"],
            "institution": [
                "hospital",
                "hospital",
                "primary_care",
                "hospital",
                "hospital",
            ],
            "admission_date": ["2023-12-30", None, "2024-01-02", None, None],
            "specimen": ["urine", "blood", "urine", "urine", "urine"],
            "specimen_fi": ["virtsa", "veri", "virtsa", "virtsa", "virtsa"],
            "result": ["positive", "positive", "negative", "negative", "positive"],
            "n_isolates": [1, 1, 0, 1, 1],
        },
        schema=SCHEMAS["cultures.csv"],
    )
    isolates = pl.DataFrame(
        {
            "isolate_id": ["C1-1", "C2-1", "C4-1", "C5-1"],
            "culture_id": ["C1", "C2", "C4", "C5"],
            "isolate_no": [1, 1, 1, 1],
            "organism": [
                "Escherichia coli",
                "Staphylococcus aureus",
                "Escherichia coli",
                "Escherichia coli",
            ],
            "quantity": [">=10^5", ">=10^5", ">=10^5", ">=10^5"],
            "esbl": [0, 0, 0, 0],
            "mrsa": [0, 1, 0, 1],
            "vre": [0, 0, 0, 0],
            "cpe": [0, 0, 0, 0],
        },
        schema=SCHEMAS["isolates.csv"],
    )
    susceptibility = pl.DataFrame(
        {
            "isolate_id": ["C1-1", "C1-1", "C2-1", "C2-1", "C2-1", "C4-1", "C5-1"],
            "culture_id": ["C1", "C1", "C2", "C2", "C2", "C4", "C5"],
            "organism": [
                "Escherichia coli",
                "Escherichia coli",
                "Staphylococcus aureus",
                "Staphylococcus aureus",
                "Staphylococcus aureus",
                "Escherichia coli",
                "Escherichia coli",
            ],
            "antibiotic": [
                "ampicillin",
                "mecillinam",
                "cefoxitin (screen)",
                "vancomycin",
                "mecillinam",
                "ampicillin",
                "ampicillin",
            ],
            "antibiotic_code": ["AMP", "MEC", "FOX", "VAN", "MEC", "AMP", "AMP"],
            "antibiotic_fi": [
                "ampisilliini",
                "mesillinaami",
                "kefoksitiini (seulonta)",
                "vankomysiini",
                "mesillinaami",
                "ampisilliini",
                "ampisilliini",
            ],
            "result": ["R", "S", "S", "S", "S", "R", "R"],
            "guideline": ["EUCAST 2023"] * 7,
        },
        schema=SCHEMAS["susceptibility.csv"],
    )
    antibiotics = pl.DataFrame(
        {
            "antibiotic": [
                "ampicillin",
                "mecillinam",
                "cefoxitin (screen)",
                "vancomycin",
            ],
            "antibiotic_code": ["AMP", "MEC", "FOX", "VAN"],
            "antibiotic_fi": [
                "ampisilliini",
                "mesillinaami",
                "kefoksitiini (seulonta)",
                "vankomysiini",
            ],
            "class": ["penicillins", "penicillins", "MRSA screen", "glycopeptides"],
            "reported_for": ["all", "urine", "all", "all"],
        },
        schema=SCHEMAS["antibiotics.csv"],
    )
    wards = pl.DataFrame(
        {
            "ward_code": ["MED-A", "ICU", "PHC-N", "MED-B"],
            "ward_fi": [
                "Sisätaudit A",
                "Teho-osasto",
                "Terveysasema Pohjoinen",
                "Sisätaudit B",
            ],
            "ward_en": [
                "Internal medicine A",
                "Intensive care unit",
                "Health centre North",
                "Internal medicine B",
            ],
            "ward_type": ["in", "in", "out", "in"],
            "institution": ["hospital", "hospital", "primary_care", "hospital"],
        },
        schema=SCHEMAS["wards.csv"],
    )
    return {
        "patients.csv": patients,
        "cultures.csv": cultures,
        "isolates.csv": isolates,
        "susceptibility.csv": susceptibility,
        "antibiotics.csv": antibiotics,
        "wards.csv": wards,
    }


def write_dataset(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name, frame in small_frames().items():
        frame.write_csv(directory / name)
    return directory


@pytest.fixture
def dataset_dir(tmp_path: Path) -> Path:
    return write_dataset(tmp_path / "data")


@pytest.fixture
def settings(dataset_dir: Path, tmp_path: Path) -> Settings:
    return replace(Settings(), data_dir=dataset_dir, out_dir=tmp_path / "output")
