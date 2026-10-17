from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl
from resistance_analysis.antibiogram import _entry, _traffic_light, build_antibiogram
from resistance_analysis.config import Settings


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
