from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import polars as pl


@dataclass(frozen=True)
class AntibioticMetadata:
    """Antibiotic metadata derived only from antibiotics.csv."""

    antibiotic: str
    antibiotic_code: str
    antibiotic_class: str
    reported_for: str
    role: str


def _normalized(value: str | None) -> str:
    return (value or "").strip().lower()


def is_screen(antibiotic_class: str | None, name: str | None = None) -> bool:
    """A screen agent is identified by its class or name in antibiotics.csv."""
    return "screen" in _normalized(antibiotic_class) or "seulonta" in _normalized(name)


def metadata_from_row(row: Mapping[str, Any]) -> AntibioticMetadata:
    antibiotic_class = row.get("class") or "unknown"
    name = row.get("antibiotic") or row.get("antibiotic_code") or "unknown"
    return AntibioticMetadata(
        antibiotic=name,
        antibiotic_code=row["antibiotic_code"],
        antibiotic_class=antibiotic_class,
        reported_for=row.get("reported_for") or "all",
        role="screen" if is_screen(antibiotic_class, name) else "therapeutic",
    )


def metadata_by_code(
    antibiotics: pl.DataFrame,
) -> dict[str, AntibioticMetadata]:
    return {
        row["antibiotic_code"]: metadata_from_row(row)
        for row in antibiotics.iter_rows(named=True)
    }
