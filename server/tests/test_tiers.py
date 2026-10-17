from __future__ import annotations

import polars as pl
from resistance_core.tiers import TierModel


def _antibiotics() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "antibiotic": ["ampicillin", "nitrofurantoin", "cefoxitin (screen)"],
            "antibiotic_code": ["AMP", "NIT", "FOX"],
            "class": ["penicillins", "nitrofurans", "MRSA screen"],
            "reported_for": ["all", "urine", "all"],
        }
    )


def _frame() -> pl.DataFrame:
    rows = []
    for index in range(10):
        rows.append(
            {
                "organism": "Escherichia coli",
                "antibiotic": "ampicillin",
                "antibiotic_code": "AMP",
                "specimen": "urine",
                "is_r": index < 8,
                "ward_code": "WARD1" if index < 5 else "WARD2",
            }
        )
        rows.append(
            {
                "organism": "Escherichia coli",
                "antibiotic": "nitrofurantoin",
                "antibiotic_code": "NIT",
                "specimen": "urine",
                "is_r": False,
                "ward_code": "WARD1" if index < 5 else "WARD2",
            }
        )
    rows.append(
        {
            "organism": "Staphylococcus aureus",
            "antibiotic": "cefoxitin (screen)",
            "antibiotic_code": "FOX",
            "specimen": "blood",
            "is_r": False,
            "ward_code": "WARD1",
        }
    )
    return pl.DataFrame(rows)


def test_observed_rate_and_interval() -> None:
    model = TierModel(_frame(), _antibiotics())
    observed, n, low, high = model.observe("Escherichia coli", "ampicillin", "urine")
    assert n == 10
    assert observed == 0.8
    assert low < observed < high


def test_tiers_are_ordered_and_respect_specimen() -> None:
    model = TierModel(_frame(), _antibiotics())
    urine = model.tiers_for("Escherichia coli", "urine")
    by_antibiotic = {entry["antibiotic"]: entry for entry in urine}
    assert by_antibiotic["nitrofurantoin"]["observed_resistance"] == 0.0
    assert by_antibiotic["ampicillin"]["observed_resistance"] == 0.8
    assert urine[0]["antibiotic"] == "nitrofurantoin"

    blood = model.tiers_for("Escherichia coli", "blood")
    assert blood == []


def test_tier_model_uses_ward_context() -> None:
    model = TierModel(_frame(), _antibiotics())
    ward1 = model.tiers_for("Escherichia coli", "urine", ward_code="WARD1")[0]
    assert ward1["observed_source"] == "ward"
    assert ward1["observed_n"] == 5
    assert ward1["observed_resistance"] == 0.0
    assert ward1["overall_n"] == 10


def test_screens_are_separated() -> None:
    model = TierModel(_frame(), _antibiotics())
    assert model.tiers_for("Staphylococcus aureus", "blood") == []
    with_screens = model.tiers_for(
        "Staphylococcus aureus", "blood", include_screens=True
    )
    assert {entry["antibiotic_code"] for entry in with_screens} == {"FOX"}
    assert with_screens[0]["role"] == "screen"


def test_all_base_tiers_covers_every_organism_specimen_pair() -> None:
    tiers = TierModel(_frame(), _antibiotics()).all_base_tiers()
    assert "Escherichia coli|urine" in tiers
    assert "Escherichia coli|blood" not in tiers
