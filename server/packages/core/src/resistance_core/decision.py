from __future__ import annotations

from typing import Any

from .antibiotic_properties import AntibioticMetadata

WARNING_PRIOR_RESISTANT = "PRIOR_RESISTANT"
WARNING_URINE_ONLY = "URINE_ONLY"
WARNING_SCREEN = "SCREEN_AGENT"

EXCLUSION_NOT_REPORTED_FOR_SPECIMEN = "not_reported_for_specimen"
EXCLUSION_NO_SPECIMEN_DATA = "no_specimen_data"


def warnings_for(
    metadata: AntibioticMetadata, prior_resistant: bool = False
) -> list[dict[str, str]]:
    """Warnings derived only from the dataset."""
    warnings: list[dict[str, str]] = []
    if metadata.reported_for == "urine":
        warnings.append(
            {
                "code": WARNING_URINE_ONLY,
                "severity": "info",
                "message": "Reported for urine specimens only.",
            }
        )
    if metadata.role == "screen":
        warnings.append(
            {
                "code": WARNING_SCREEN,
                "severity": "info",
                "message": "Screening agent; not a treatment option.",
            }
        )
    if prior_resistant:
        warnings.append(
            {
                "code": WARNING_PRIOR_RESISTANT,
                "severity": "warning",
                "message": "The patient's prior isolate of this organism was resistant.",
            }
        )
    return warnings


def _ci(entry: dict[str, Any]) -> tuple[float | None, float | None]:
    low = entry.get("observed_ci_low")
    high = entry.get("observed_ci_high")
    if low is None or high is None:
        return None, None
    return float(low), float(high)


def rank_options(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assign rank and rank_group, grouping options whose intervals overlap.

    Options are expected to be sorted by the caller. Ranking is the ordinal
    position; ``rank_group`` is 1-based and shared by statistically
    indistinguishable options.
    """
    group = 0
    group_high: float | None = None
    for index, entry in enumerate(options, start=1):
        entry["rank"] = index
        low, high = _ci(entry)
        if low is None or high is None:
            group += 1
            group_high = None
        elif group_high is None or low > group_high:
            group += 1
            group_high = high
        else:
            group_high = max(group_high, high)
        entry["rank_group"] = group
    return options
