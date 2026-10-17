from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl

from .antibiotic_properties import metadata_by_code
from .stats import wilson_interval

BASE_KEYS = ("organism", "antibiotic", "specimen")


@dataclass
class Antibiotic:
    antibiotic: str
    antibiotic_code: str
    antibiotic_class: str
    reported_for: str
    role: str


class TierModel:
    """Observed-resistance evidence over the susceptibility data.

    This model makes no smoothing or threshold choices. It reports the
    observed rate, count and Wilson interval for the requested context and for
    the overall specimen, both derived only from the dataset.
    """

    def __init__(self, ab_analytics: pl.DataFrame, antibiotics: pl.DataFrame) -> None:
        columns = ["organism", "antibiotic", "antibiotic_code", "specimen", "is_r"]
        if "ward_code" in ab_analytics.columns:
            columns.append("ward_code")
        self._frame = ab_analytics.select(columns)
        self._cache: dict[tuple, tuple[float, int]] = {}
        metadata = metadata_by_code(antibiotics)
        self.antibiotics = [
            Antibiotic(
                antibiotic=row["antibiotic"],
                antibiotic_code=row["antibiotic_code"],
                antibiotic_class=row.get("class") or "unknown",
                reported_for=row.get("reported_for") or "all",
                role=metadata[row["antibiotic_code"]].role,
            )
            for row in antibiotics.iter_rows(named=True)
        ]

    def _counts(self, keys: dict[str, Any]) -> tuple[float, int]:
        cache_key = tuple(sorted((key, str(value)) for key, value in keys.items()))
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        expr = pl.lit(True)
        for column, value in keys.items():
            if column not in self._frame.columns:
                continue
            expr = expr & (pl.col(column) == value)
        sub = self._frame.filter(expr)
        result = (float(sub["is_r"].sum()), sub.height)
        self._cache[cache_key] = result
        return result

    def observe(
        self,
        organism: str,
        antibiotic: str,
        specimen: str | None = None,
        ward_code: str | None = None,
    ) -> tuple[float | None, int, float | None, float | None]:
        keys: dict[str, Any] = {"organism": organism, "antibiotic": antibiotic}
        if specimen is not None:
            keys["specimen"] = specimen
        if ward_code is not None:
            keys["ward_code"] = ward_code
        positives, n = self._counts(keys)
        if n == 0:
            return (None, 0, None, None)
        low, high = wilson_interval(int(positives), n)
        return (positives / n, n, low, high)

    def _applicable(self, antibiotic: Antibiotic, specimen: str) -> bool:
        return antibiotic.reported_for in ("all", specimen)

    def _has_organism_antibiotic(
        self, organism: str, antibiotic: str, specimen: str
    ) -> bool:
        _, n = self._counts(
            {"organism": organism, "antibiotic": antibiotic, "specimen": specimen}
        )
        return n > 0

    def _entry(
        self,
        antibiotic: Antibiotic,
        organism: str,
        specimen: str,
        ward_code: str | None,
    ) -> dict[str, Any]:
        observed, observed_n, observed_low, observed_high = self.observe(
            organism, antibiotic.antibiotic, specimen, ward_code
        )
        overall, overall_n, overall_low, overall_high = self.observe(
            organism, antibiotic.antibiotic, specimen
        )
        observed_source = "ward" if ward_code and observed_n else "overall"
        return {
            "antibiotic": antibiotic.antibiotic,
            "antibiotic_code": antibiotic.antibiotic_code,
            "class": antibiotic.antibiotic_class,
            "reported_for": antibiotic.reported_for,
            "role": antibiotic.role,
            "observed_resistance": round(observed, 4) if observed is not None else None,
            "observed_n": observed_n,
            "observed_ci_low": round(observed_low, 4)
            if observed_low is not None
            else None,
            "observed_ci_high": round(observed_high, 4)
            if observed_high is not None
            else None,
            "observed_source": observed_source,
            "overall_resistance": round(overall, 4) if overall is not None else None,
            "overall_n": overall_n,
            "overall_ci_low": round(overall_low, 4)
            if overall_low is not None
            else None,
            "overall_ci_high": round(overall_high, 4)
            if overall_high is not None
            else None,
        }

    def tiers_for(
        self,
        organism: str,
        specimen: str,
        ward_code: str | None = None,
        include_screens: bool = False,
    ) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for antibiotic in self.antibiotics:
            if antibiotic.role == "screen" and not include_screens:
                continue
            if not self._applicable(antibiotic, specimen):
                continue
            if not self._has_organism_antibiotic(
                organism, antibiotic.antibiotic, specimen
            ):
                continue
            entries.append(self._entry(antibiotic, organism, specimen, ward_code))
        entries.sort(
            key=lambda entry: (
                entry["observed_resistance"]
                if entry["observed_resistance"] is not None
                else 1.0,
                entry["antibiotic"],
            )
        )
        return entries

    def all_base_tiers(self) -> dict[str, list[dict[str, Any]]]:
        keys = (
            self._frame.select("organism", "specimen")
            .unique()
            .sort("organism", "specimen")
        )
        tiers: dict[str, list[dict[str, Any]]] = {}
        for organism, specimen in keys.iter_rows():
            tiers[f"{organism}|{specimen}"] = self.tiers_for(organism, specimen)
        return tiers
