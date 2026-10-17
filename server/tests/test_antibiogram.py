from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl

from resistance.antibiogram import _entry, _traffic_light, build_antibiogram
from resistance.config import Settings


def _frames(
    isolates: list[dict[str, Any]],
    susceptibility: list[dict[str, Any]],
    contexts: list[dict[str, Any]],
) -> tuple[pl.DataFrame, ...]:
    isolate_frame = pl.DataFrame(isolates)
    ab_frame = pl.DataFrame(susceptibility)
    context_frame = pl.DataFrame(contexts)
    patients = (
        isolate_frame.select("patient_id", "home_area").unique().sort("patient_id")
    )
    wards = pl.DataFrame(
        {
            "ward_code": ["MED-A"],
            "ward_fi": ["Sisätaudit A"],
            "ward_en": ["Internal medicine A"],
            "ward_type": ["in"],
        }
    )
    antibiotics = pl.DataFrame(
        {
            "antibiotic": ["ampicillin", "mecillinam", "cefoxitin (screen)"],
            "antibiotic_code": ["AMP", "MEC", "FOX"],
            "class": ["penicillins", "penicillins", "MRSA screen"],
            "reported_for": ["all", "urine", "all"],
        }
    )
    # Order matches build_antibiogram(contexts, isolates, ab, patients, wards, antibiotics).
    return context_frame, isolate_frame, ab_frame, patients, wards, antibiotics


def _isolate(
    isolate_id: str,
    patient_id: str,
    organism: str,
    specimen: str,
    sample_date: date,
    ward_type: str,
    ward_code: str,
    home_area: str,
) -> dict[str, Any]:
    return {
        "isolate_id": isolate_id,
        "patient_id": patient_id,
        "organism": organism,
        "specimen": specimen,
        "sample_date": sample_date,
        "ward_type": ward_type,
        "ward_code": ward_code,
        "home_area": home_area,
    }


def _result(
    isolate_id: str,
    organism: str,
    specimen: str,
    antibiotic: str,
    antibiotic_code: str,
    antibiotic_class: str,
    reported_for: str,
    is_s: bool,
    ward_type: str,
    ward_code: str,
    home_area: str,
    days_since_admission: int | None = None,
) -> dict[str, Any]:
    return {
        "isolate_id": isolate_id,
        "organism": organism,
        "specimen": specimen,
        "antibiotic": antibiotic,
        "antibiotic_code": antibiotic_code,
        "class": antibiotic_class,
        "reported_for": reported_for,
        "is_s": is_s,
        "ward_type": ward_type,
        "ward_code": ward_code,
        "home_area": home_area,
        "days_since_admission": days_since_admission,
    }


def _scenario():
    isolates = [
        _isolate(
            "I1",
            "P1",
            "Escherichia coli",
            "urine",
            date(2023, 6, 1),
            "in",
            "MED-A",
            "Centre",
        ),
        _isolate(
            "I2",
            "P1",
            "Escherichia coli",
            "urine",
            date(2024, 6, 1),
            "in",
            "MED-A",
            "Centre",
        ),
        _isolate(
            "I3",
            "P2",
            "Escherichia coli",
            "urine",
            date(2024, 6, 2),
            "out",
            "PHC-N",
            "Centre",
        ),
    ]
    susceptibility = [
        _result(
            "I1",
            "Escherichia coli",
            "urine",
            "ampicillin",
            "AMP",
            "penicillins",
            "all",
            True,
            "in",
            "MED-A",
            "Centre",
        ),
        _result(
            "I2",
            "Escherichia coli",
            "urine",
            "ampicillin",
            "AMP",
            "penicillins",
            "all",
            False,
            "in",
            "MED-A",
            "Centre",
        ),
        _result(
            "I3",
            "Escherichia coli",
            "urine",
            "ampicillin",
            "AMP",
            "penicillins",
            "all",
            True,
            "out",
            "PHC-N",
            "Centre",
        ),
    ]
    contexts = [
        {
            "culture_id": "c1",
            "patient_id": "P1",
            "ward_type": "in",
            "sample_date": date(2023, 6, 1),
        },
        {
            "culture_id": "c3",
            "patient_id": "P2",
            "ward_type": "out",
            "sample_date": date(2024, 6, 2),
        },
    ]
    return _frames(isolates, susceptibility, contexts), Settings()


def test_periods_and_first_isolate_per_period() -> None:
    frames, settings = _scenario()
    result = build_antibiogram(*frames, settings)

    assert result.periods == ["annual:2023", "annual:2024", "last4w"]
    assert result.data_as_of == date(2024, 6, 2)

    # A patient contributes one isolate per year, ordered by sample_date then id.
    first_2023 = result.matrix["hospital|-|annual:2023"]["Escherichia coli|urine"][0]
    assert first_2023["n"] == 1
    assert first_2023["n_s"] == 1
    assert first_2023["susceptibility_rate"] is None
    assert first_2023["traffic_light"] == "none"

    # In 2024 P1's first isolate is I2 (R); P2 contributes I3 (S).
    annual_2024 = result.matrix["hospital|-|annual:2024"]["Escherichia coli|urine"][0]
    assert annual_2024["n"] == 2
    assert annual_2024["n_s"] == 1

    last4w = result.matrix["hospital|-|last4w"]["Escherichia coli|urine"][0]
    assert last4w["n"] == 2
    assert last4w["n_s"] == 1


def test_scope_breakdown_and_region_units() -> None:
    frames, settings = _scenario()
    result = build_antibiogram(*frames, settings)

    assert (
        result.matrix["ward|MED-A|annual:2024"]["Escherichia coli|urine"][0]["n"] == 1
    )
    assert result.matrix["region|Centre|last4w"]["Escherichia coli|urine"][0]["n"] == 1
    assert "hospital|-|annual:2024" in result.matrix

    assert [ward["unit"] for ward in result.scopes["ward"]] == ["MED-A"]
    assert [region["unit"] for region in result.scopes["region"]] == ["Centre"]


def test_first_isolate_rule_is_applied_per_setting() -> None:
    isolates = [
        # P1: outpatient isolate first, inpatient later.
        _isolate(
            "O1",
            "P1",
            "Escherichia coli",
            "urine",
            date(2024, 6, 1),
            "out",
            "PHC-N",
            "Centre",
        ),
        _isolate(
            "N1",
            "P1",
            "Escherichia coli",
            "urine",
            date(2024, 6, 10),
            "in",
            "MED-A",
            "Centre",
        ),
        # P2: inpatient isolate first, outpatient later.
        _isolate(
            "N2",
            "P2",
            "Escherichia coli",
            "urine",
            date(2024, 6, 2),
            "in",
            "MED-A",
            "East",
        ),
        _isolate(
            "O2",
            "P2",
            "Escherichia coli",
            "urine",
            date(2024, 6, 11),
            "out",
            "PHC-N",
            "East",
        ),
    ]
    susceptibility = [
        _result(
            "O1",
            "Escherichia coli",
            "urine",
            "ampicillin",
            "AMP",
            "penicillins",
            "all",
            True,
            "out",
            "PHC-N",
            "Centre",
        ),
        _result(
            "N1",
            "Escherichia coli",
            "urine",
            "ampicillin",
            "AMP",
            "penicillins",
            "all",
            False,
            "in",
            "MED-A",
            "Centre",
        ),
        _result(
            "N2",
            "Escherichia coli",
            "urine",
            "ampicillin",
            "AMP",
            "penicillins",
            "all",
            False,
            "in",
            "MED-A",
            "East",
        ),
        _result(
            "O2",
            "Escherichia coli",
            "urine",
            "ampicillin",
            "AMP",
            "penicillins",
            "all",
            True,
            "out",
            "PHC-N",
            "East",
        ),
    ]
    contexts = [
        {
            "culture_id": "co1",
            "patient_id": "P1",
            "ward_type": "out",
            "sample_date": date(2024, 6, 1),
        },
        {
            "culture_id": "cn1",
            "patient_id": "P1",
            "ward_type": "in",
            "sample_date": date(2024, 6, 10),
        },
        {
            "culture_id": "cn2",
            "patient_id": "P2",
            "ward_type": "in",
            "sample_date": date(2024, 6, 2),
        },
        {
            "culture_id": "co2",
            "patient_id": "P2",
            "ward_type": "out",
            "sample_date": date(2024, 6, 11),
        },
    ]
    frames = _frames(isolates, susceptibility, contexts)
    result = build_antibiogram(*frames, Settings())

    # Each setting keeps its own first isolate, so neither setting suppresses the other.
    ward = result.matrix["ward|MED-A|annual:2024"]["Escherichia coli|urine"][0]
    assert ward["n"] == 2
    assert ward["n_s"] == 0  # N1 and N2, both R

    centre = result.matrix["region|Centre|annual:2024"]["Escherichia coli|urine"][0]
    assert centre["n"] == 1
    assert centre["n_s"] == 1  # O1, S

    east = result.matrix["region|East|annual:2024"]["Escherichia coli|urine"][0]
    assert east["n"] == 1
    assert east["n_s"] == 1  # O2, S

    # The hospital scope spans settings and counts one global first isolate per patient.
    hospital = result.matrix["hospital|-|annual:2024"]["Escherichia coli|urine"][0]
    assert hospital["n"] == 2
    assert hospital["n_s"] == 1  # O1 (S) and N2 (R)


def test_inpatient_onset_scopes_split_by_days_since_admission() -> None:
    isolates = [
        _isolate(
            "E1",
            "P1",
            "Escherichia coli",
            "urine",
            date(2024, 6, 1),
            "in",
            "MED-A",
            "Centre",
        ),
        _isolate(
            "E2",
            "P2",
            "Escherichia coli",
            "urine",
            date(2024, 6, 2),
            "in",
            "MED-A",
            "Centre",
        ),
        _isolate(
            "E3",
            "P3",
            "Escherichia coli",
            "urine",
            date(2024, 6, 3),
            "in",
            "MED-A",
            "Centre",
        ),
        _isolate(
            "E4",
            "P4",
            "Escherichia coli",
            "urine",
            date(2024, 6, 4),
            "in",
            "MED-A",
            "Centre",
        ),
    ]

    def result_for(isolate_id: str, is_s: bool, days: int | None) -> dict[str, Any]:
        return _result(
            isolate_id,
            "Escherichia coli",
            "urine",
            "ampicillin",
            "AMP",
            "penicillins",
            "all",
            is_s,
            "in",
            "MED-A",
            "Centre",
            days_since_admission=days,
        )

    susceptibility = [
        result_for("E1", True, 0),
        result_for("E2", False, 2),
        result_for("E3", False, 3),
        result_for("E4", True, None),
    ]
    contexts = [
        {
            "culture_id": f"c{index}",
            "patient_id": f"P{index}",
            "ward_type": "in",
            "sample_date": date(2024, 6, index),
        }
        for index in range(1, 5)
    ]
    frames = _frames(isolates, susceptibility, contexts)
    antibiogram = build_antibiogram(*frames, Settings())

    def cell(scope: str) -> dict[str, Any]:
        return antibiogram.matrix[f"{scope}|MED-A|annual:2024"][
            "Escherichia coli|urine"
        ][0]

    # Onset sub-scopes partition the inpatient isolates at the 3-day rule.
    assert cell("ward-early")["n"] == 2  # days 0 and 2
    assert cell("ward-early")["n_s"] == 1
    assert cell("ward-late")["n"] == 1  # day 3
    assert cell("ward-late")["n_s"] == 0
    # The whole-ward scope keeps every inpatient, including the missing admission date.
    assert cell("ward")["n"] == 4
    assert cell("ward")["n_s"] == 2

    assert [unit["unit"] for unit in antibiogram.scopes["ward-early"]] == ["MED-A"]
    assert [unit["unit"] for unit in antibiogram.scopes["ward-late"]] == ["MED-A"]


def test_applicability_and_screens_are_kept_with_role() -> None:
    isolates = [
        _isolate(
            "I4",
            "P3",
            "Staphylococcus aureus",
            "blood",
            date(2024, 7, 1),
            "in",
            "MED-A",
            "East",
        ),
    ]
    susceptibility = [
        _result(
            "I4",
            "Staphylococcus aureus",
            "blood",
            "ampicillin",
            "AMP",
            "penicillins",
            "all",
            True,
            "in",
            "MED-A",
            "East",
        ),
        _result(
            "I4",
            "Staphylococcus aureus",
            "blood",
            "cefoxitin (screen)",
            "FOX",
            "MRSA screen",
            "all",
            True,
            "in",
            "MED-A",
            "East",
        ),
        # A urine-only agent on a blood specimen must be filtered out.
        _result(
            "I4",
            "Staphylococcus aureus",
            "blood",
            "mecillinam",
            "MEC",
            "penicillins",
            "urine",
            True,
            "in",
            "MED-A",
            "East",
        ),
    ]
    contexts = [
        {
            "culture_id": "c4",
            "patient_id": "P3",
            "ward_type": "in",
            "sample_date": date(2024, 7, 1),
        }
    ]
    frames = _frames(isolates, susceptibility, contexts)
    result = build_antibiogram(*frames, Settings())

    entries = result.matrix["hospital|-|annual:2024"]["Staphylococcus aureus|blood"]
    by_code = {entry["antibiotic_code"]: entry for entry in entries}
    assert set(by_code) == {"AMP", "FOX"}
    assert by_code["FOX"]["role"] == "screen"


def test_entry_thresholds_and_traffic_light_cutoffs() -> None:
    settings = Settings()

    def row(n: int, n_s: int) -> dict[str, Any]:
        return {
            "antibiotic": "ampicillin",
            "antibiotic_code": "AMP",
            "class": "penicillins",
            "reported_for": "all",
            "n": n,
            "n_s": n_s,
        }

    assert _entry(row(100, 80), "therapeutic", settings)["traffic_light"] == "yellow"
    assert _entry(row(100, 81), "therapeutic", settings)["traffic_light"] == "green"
    assert _entry(row(100, 60), "therapeutic", settings)["traffic_light"] == "red"
    assert _entry(row(100, 61), "therapeutic", settings)["traffic_light"] == "yellow"

    reported = _entry(row(100, 80), "therapeutic", settings)
    assert "ci_low" not in reported
    assert "ci_high" not in reported

    small = _entry(row(29, 20), "therapeutic", settings)
    assert small["susceptibility_rate"] is None
    assert small["traffic_light"] == "none"

    assert _traffic_light(0.5, settings) == "red"
    assert _traffic_light(0.9, settings) == "green"
