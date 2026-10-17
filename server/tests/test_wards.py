from __future__ import annotations

import polars as pl
from resistance_analysis.wards import build_ward_summaries


def _frames():
    contexts = pl.DataFrame(
        {
            "ward_code": ["MED-A", "MED-A"],
            "patient_id": ["P1", "P2"],
            "sample_date": ["2024-01-01", "2024-01-02"],
            "specimen": ["urine", "urine"],
            "result": ["positive", "positive"],
        }
    ).with_columns(pl.col("sample_date").str.to_date())

    analysis = pl.DataFrame(
        {
            "ward_code": ["MED-A", "MED-A", "MED-A"],
            "isolate_id": ["I1", "I2", "I3"],
            "organism": [
                "Escherichia coli",
                "Escherichia coli",
                "Staphylococcus aureus",
            ],
            "esbl": [1, 0, 0],
            "mrsa": [0, 0, 1],
            "vre": [0, 0, 0],
            "cpe": [0, 0, 0],
        }
    )

    ab_analysis = pl.DataFrame(
        {
            "ward_code": ["MED-A"] * 7,
            "isolate_id": ["I1", "I1", "I1", "I2", "I2", "I2", "I3"],
            "specimen": ["urine"] * 7,
            "organism": [
                "Escherichia coli",
                "Escherichia coli",
                "Escherichia coli",
                "Escherichia coli",
                "Escherichia coli",
                "Escherichia coli",
                "Staphylococcus aureus",
            ],
            "antibiotic": [
                "ampicillin",
                "nitrofurantoin",
                "cefuroxime",
                "ampicillin",
                "nitrofurantoin",
                "cefuroxime",
                "cefoxitin (screen)",
            ],
            "antibiotic_code": ["AMP", "NIT", "CXM", "AMP", "NIT", "CXM", "FOX"],
            "class": [
                "penicillins",
                "nitrofurans",
                "cephalosporins 2nd gen",
                "penicillins",
                "nitrofurans",
                "cephalosporins 2nd gen",
                "MRSA screen",
            ],
            "is_r": [True, False, True, False, False, False, True],
        }
    )

    antibiotics = pl.DataFrame(
        {
            "antibiotic": [
                "ampicillin",
                "nitrofurantoin",
                "cefoxitin (screen)",
                "cefuroxime",
            ],
            "antibiotic_code": ["AMP", "NIT", "FOX", "CXM"],
            "class": [
                "penicillins",
                "nitrofurans",
                "MRSA screen",
                "cephalosporins 2nd gen",
            ],
            "reported_for": ["all", "urine", "all", "all"],
        }
    )

    wards_meta = pl.DataFrame(
        {
            "ward_code": ["MED-A"],
            "ward_fi": ["Sisätaudit A"],
            "ward_en": ["Internal medicine A"],
            "ward_type": ["in"],
            "institution": ["hospital"],
        }
    )
    return contexts, analysis, ab_analysis, wards_meta, antibiotics


def test_ward_summary_volumes_and_organisms() -> None:
    contexts, analysis, ab_analysis, wards_meta, antibiotics = _frames()
    ward = build_ward_summaries(
        contexts, analysis, ab_analysis, wards_meta, antibiotics
    )["MED-A"]
    assert ward["counts"] == {
        "patients": 2,
        "cultures": 2,
        "isolates": 3,
        "susceptibility_results": 7,
    }
    assert ward["organisms"][0]["organism"] == "Escherichia coli"
    assert ward["organisms"][0]["isolates"] == 2


def test_flag_rates_use_marker_denominator() -> None:
    contexts, analysis, ab_analysis, wards_meta, antibiotics = _frames()
    ward = build_ward_summaries(
        contexts, analysis, ab_analysis, wards_meta, antibiotics
    )["MED-A"]
    flags = ward["flag_rates_by_organism"]
    assert flags["Escherichia coli"]["esbl"]["n"] == 2
    assert flags["Escherichia coli"]["esbl"]["n_pos"] == 1
    assert flags["Escherichia coli"]["esbl"]["marker_antibiotic_codes"] == ["CXM"]
    assert flags["Staphylococcus aureus"]["mrsa"]["n"] == 1
    assert flags["Staphylococcus aureus"]["mrsa"]["n_pos"] == 1
    assert "vre" not in flags["Staphylococcus aureus"]  # no VAN marker tested


def test_antibiogram_is_organism_stratified_and_excludes_screens() -> None:
    contexts, analysis, ab_analysis, wards_meta, antibiotics = _frames()
    ward = build_ward_summaries(
        contexts, analysis, ab_analysis, wards_meta, antibiotics
    )["MED-A"]
    antibiogram = ward["antibiogram"]["urine"]
    assert set(antibiogram) == {"Escherichia coli"}
    codes = [entry["antibiotic_code"] for entry in antibiogram["Escherichia coli"]]
    assert codes == ["NIT", "AMP", "CXM"]
    assert all(
        entry["role"] != "screen"
        for entries in antibiogram.values()
        for entry in entries
    )


def test_resistance_by_specimen_is_sorted_by_rate() -> None:
    contexts, analysis, ab_analysis, wards_meta, antibiotics = _frames()
    ward = build_ward_summaries(
        contexts, analysis, ab_analysis, wards_meta, antibiotics
    )["MED-A"]
    urine = ward["resistance_by_antibiotic"]["urine"]
    assert [entry["antibiotic_code"] for entry in urine] == ["NIT", "AMP", "CXM"]
    assert urine[0]["rate"] == 0.0
    assert urine[1]["rate"] == 0.5
