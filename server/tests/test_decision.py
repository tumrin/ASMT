from __future__ import annotations

import polars as pl
from resistance_core.antibiotic_properties import (
    is_screen,
    marker_codes,
    marker_flags_for,
    metadata_from_row,
)
from resistance_core.decision import rank_options, warnings_for


def _antibiotics() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "antibiotic": [
                "ampicillin",
                "nitrofurantoin",
                "cefoxitin (screen)",
                "vancomycin",
                "cefuroxime",
                "meropenem",
            ],
            "antibiotic_code": ["AMP", "NIT", "FOX", "VAN", "CXM", "MEM"],
            "class": [
                "penicillins",
                "nitrofurans",
                "MRSA screen",
                "glycopeptides",
                "cephalosporins 2nd gen",
                "carbapenems",
            ],
            "reported_for": ["all", "urine", "all", "all", "all", "all"],
        }
    )


def test_screen_role_is_derived_from_class_or_name() -> None:
    assert is_screen("MRSA screen", "cefoxitin (screen)")
    assert not is_screen("penicillins", "ampicillin")


def test_marker_flags_are_derived_from_class_and_name() -> None:
    assert marker_flags_for("MRSA screen", "cefoxitin (screen)") == ("mrsa",)
    assert marker_flags_for("glycopeptides", "vancomycin") == ("vre",)
    assert marker_flags_for("cephalosporins 2nd gen", "cefuroxime") == ("esbl",)
    assert marker_flags_for("carbapenems", "meropenem") == ("cpe",)


def test_marker_codes_map_flags_to_antibiotics() -> None:
    markers = marker_codes(_antibiotics())
    assert markers["mrsa"] == ("FOX",)
    assert markers["vre"] == ("VAN",)
    assert markers["esbl"] == ("CXM",)
    assert markers["cpe"] == ("MEM",)


def test_metadata_from_row_contains_only_dataset_fields() -> None:
    row = {
        "antibiotic": "nitrofurantoin",
        "antibiotic_code": "NIT",
        "class": "nitrofurans",
        "reported_for": "urine",
    }
    meta = metadata_from_row(row)
    assert meta.role == "therapeutic"
    assert meta.reported_for == "urine"
    assert meta.marker_flags == ()


def test_warnings_are_dataset_derived() -> None:
    meta = metadata_from_row(
        {
            "antibiotic": "nitrofurantoin",
            "antibiotic_code": "NIT",
            "class": "nitrofurans",
            "reported_for": "urine",
        }
    )
    codes = {warning["code"] for warning in warnings_for(meta, prior_resistant=True)}
    assert codes == {"URINE_ONLY", "PRIOR_RESISTANT"}


def test_rank_options_groups_overlapping_intervals() -> None:
    options = [
        {"antibiotic": "a", "observed_ci_low": 0.01, "observed_ci_high": 0.05},
        {"antibiotic": "b", "observed_ci_low": 0.03, "observed_ci_high": 0.08},
        {"antibiotic": "c", "observed_ci_low": 0.20, "observed_ci_high": 0.30},
    ]
    ranked = rank_options(options)
    assert [entry["rank"] for entry in ranked] == [1, 2, 3]
    assert [entry["rank_group"] for entry in ranked] == [1, 1, 2]
