from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import polars as pl

MARKER_FLAGS = ("mrsa", "vre", "esbl", "cpe")

# Marker mapping derived from the antibiotic class/name in antibiotics.csv.
MARKER_CLASS_HINTS = {
    "mrsa": ("mrsa screen",),
    "vre": ("glycopeptides",),
    "esbl": ("cephalosporins 2nd gen",),
    "cpe": ("carbapenems",),
}
MARKER_NAME_HINTS = {
    "mrsa": ("cefoxitin",),
    "vre": ("vancomycin",),
    "esbl": ("cefuroxime",),
    "cpe": ("meropenem",),
}


@dataclass(frozen=True)
class AntibioticMetadata:
    """Antibiotic metadata derived only from antibiotics.csv."""

    antibiotic: str
    antibiotic_code: str
    antibiotic_class: str
    reported_for: str
    role: str
    marker_flags: tuple[str, ...] = ()


def _normalized(value: str | None) -> str:
    return (value or "").strip().lower()


def is_screen(antibiotic_class: str | None, name: str | None = None) -> bool:
    """A screen agent is identified by its class or name in antibiotics.csv."""
    return "screen" in _normalized(antibiotic_class) or "seulonta" in _normalized(name)


def marker_flags_for(
    antibiotic_class: str | None, name: str | None = None
) -> tuple[str, ...]:
    hints = _normalized(antibiotic_class) + " " + _normalized(name)
    flags = [
        flag
        for flag, markers in MARKER_CLASS_HINTS.items()
        if any(marker in hints for marker in markers)
    ]
    for flag, markers in MARKER_NAME_HINTS.items():
        if flag not in flags and any(marker in hints for marker in markers):
            flags.append(flag)
    return tuple(flags)


def metadata_from_row(row: Mapping[str, Any]) -> AntibioticMetadata:
    antibiotic_class = row.get("class") or "unknown"
    name = row.get("antibiotic") or row.get("antibiotic_code") or "unknown"
    return AntibioticMetadata(
        antibiotic=name,
        antibiotic_code=row["antibiotic_code"],
        antibiotic_class=antibiotic_class,
        reported_for=row.get("reported_for") or "all",
        role="screen" if is_screen(antibiotic_class, name) else "therapeutic",
        marker_flags=marker_flags_for(antibiotic_class, name),
    )


def metadata_by_code(
    antibiotics: pl.DataFrame,
) -> dict[str, AntibioticMetadata]:
    return {
        row["antibiotic_code"]: metadata_from_row(row)
        for row in antibiotics.iter_rows(named=True)
    }


def marker_codes(antibiotics: pl.DataFrame) -> dict[str, tuple[str, ...]]:
    """Map each flag to the antibiotic codes that act as its marker."""
    result: dict[str, tuple[str, ...]] = {}
    metadata = metadata_by_code(antibiotics)
    for flag in MARKER_FLAGS:
        result[flag] = tuple(
            code for code, meta in metadata.items() if flag in meta.marker_flags
        )
    return result


def properties_payload(antibiotics: pl.DataFrame) -> dict[str, Any]:
    """Serialise the data-derived antibiotic metadata for the API."""
    metadata = metadata_by_code(antibiotics)
    return {
        "antibiotics": [
            {
                "antibiotic": meta.antibiotic,
                "antibiotic_code": meta.antibiotic_code,
                "class": meta.antibiotic_class,
                "reported_for": meta.reported_for,
                "role": meta.role,
                "marker_flags": list(meta.marker_flags),
            }
            for meta in metadata.values()
        ]
    }
