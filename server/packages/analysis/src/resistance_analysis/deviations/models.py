from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum

import polars as pl


class Family(str, Enum):
    CONSISTENCY = "consistency"
    STATISTICAL = "statistical"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# `unit_type` labels the record a deviation points at. Nothing is ever removed;
# these are descriptive only:
#   "flag"            -> an isolate flag (key "isolate_id:flag")
#   "susceptibility"  -> an isolate_id x antibiotic_code result
#   "isolate"         -> an isolate (key "isolate_id")
#   "culture_isolates"-> all isolates of a culture (key "culture_id")
#   "culture"         -> a culture (key "culture_id")
UNIT_FLAG = "flag"
UNIT_SUSCEPTIBILITY = "susceptibility"
UNIT_ISOLATE = "isolate"
UNIT_CULTURE_ISOLATES = "culture_isolates"
UNIT_CULTURE = "culture"


@dataclass
class Deviation:
    """One detected anomaly, reported but never applied to the data.

    `unit_type` (see the UNIT_* labels) and `unit_key` identify the record the
    deviation points at.
    """

    family: Family
    detector: str
    unit_type: str
    unit_key: str
    metric: str
    expected: str
    observed: str
    threshold: str
    severity: Severity
    detail: dict[str, object] = field(default_factory=dict)


def make_deviation(
    family: Family,
    detector: str,
    unit_type: str,
    unit_key: str,
    metric: str,
    expected: str,
    observed: str,
    threshold: str,
    severity: Severity,
    **detail: object,
) -> Deviation:
    return Deviation(
        family=family,
        detector=detector,
        unit_type=unit_type,
        unit_key=unit_key,
        metric=metric,
        expected=expected,
        observed=observed,
        threshold=threshold,
        severity=severity,
        detail=detail,
    )


LOG_SCHEMA = {
    "family": pl.String,
    "detector": pl.String,
    "unit_type": pl.String,
    "unit_key": pl.String,
    "metric": pl.String,
    "expected": pl.String,
    "observed": pl.String,
    "threshold": pl.String,
    "severity": pl.String,
    "detail": pl.String,
}


def to_frame(deviations: list[Deviation]) -> pl.DataFrame:
    if not deviations:
        return pl.DataFrame(schema=LOG_SCHEMA)
    rows = []
    for dev in deviations:
        payload = asdict(dev)
        payload["family"] = dev.family.value
        payload["severity"] = dev.severity.value
        payload["detail"] = json.dumps(dev.detail, default=str)
        rows.append(payload)
    return pl.DataFrame(rows, schema=LOG_SCHEMA)


def summarise(deviations: list[Deviation]) -> dict[str, object]:
    by_family: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_detector: dict[str, int] = {}
    for dev in deviations:
        by_family[dev.family.value] = by_family.get(dev.family.value, 0) + 1
        by_severity[dev.severity.value] = by_severity.get(dev.severity.value, 0) + 1
        by_detector[dev.detector] = by_detector.get(dev.detector, 0) + 1
    return {
        "total": len(deviations),
        "by_family": by_family,
        "by_severity": by_severity,
        "by_detector": by_detector,
    }
