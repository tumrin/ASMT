from __future__ import annotations

import polars as pl

from resistance.antibiotic_properties import (
    is_screen,
    metadata_by_code,
    metadata_from_row,
)


def _antibiotics() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "antibiotic": ["ampicillin", "nitrofurantoin", "cefoxitin (screen)"],
            "antibiotic_code": ["AMP", "NIT", "FOX"],
            "class": ["penicillins", "nitrofurans", "MRSA screen"],
            "reported_for": ["all", "urine", "all"],
        }
    )


def test_screen_role_is_derived_from_class_or_name() -> None:
    assert is_screen("MRSA screen", "cefoxitin (screen)")
    assert is_screen("penicillins", "seulonta")
    assert not is_screen("penicillins", "ampicillin")


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


def test_metadata_by_code_marks_screens() -> None:
    metadata = metadata_by_code(_antibiotics())
    assert metadata["AMP"].role == "therapeutic"
    assert metadata["FOX"].role == "screen"
