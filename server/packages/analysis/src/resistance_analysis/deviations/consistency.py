from __future__ import annotations

import polars as pl
from resistance_core.antibiotic_properties import marker_codes

from ..load import Dataset
from .models import (
    UNIT_CULTURE,
    UNIT_CULTURE_ISOLATES,
    UNIT_FLAG,
    UNIT_ISOLATE,
    UNIT_SUSCEPTIBILITY,
    Deviation,
    Family,
    Severity,
    make_deviation,
)
from .plausibility import detect as detect_plausibility

# Flags whose marker result *is* the phenotype: cefoxitin R is the MRSA screen and
# vancomycin R is vancomycin-resistant enterococcus, so a resistant marker with a
# zero flag is a genuine contradiction. ESBL and CPE are mechanism flags, not
# phenotypes: cefuroxime and meropenem resistance have other mechanisms, so a
# resistant marker there does not imply the flag.
DEFINITIONAL_FLAGS = ("mrsa", "vre")


def _dev(
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
    return make_deviation(
        Family.CONSISTENCY,
        detector,
        unit_type,
        unit_key,
        metric,
        expected,
        observed,
        threshold,
        severity,
        **detail,
    )


def _tested_isolates(susceptibility: pl.DataFrame, codes: tuple[str, ...]) -> set[str]:
    if not codes:
        return set()
    return set(
        susceptibility.filter(pl.col("antibiotic_code").is_in(codes))[
            "isolate_id"
        ].to_list()
    )


def _flag_without_marker(
    isolates: pl.DataFrame,
    susceptibility: pl.DataFrame,
    markers: dict[str, tuple[str, ...]],
) -> list[Deviation]:
    deviations: list[Deviation] = []
    for flag in ("mrsa", "vre", "esbl", "cpe"):
        flagged = isolates.filter(pl.col(flag) == 1)
        if flagged.is_empty():
            continue
        tested = _tested_isolates(susceptibility, markers.get(flag, ()))
        offenders = flagged.filter(~pl.col("isolate_id").is_in(sorted(tested)))
        for row in offenders.iter_rows(named=True):
            deviations.append(
                _dev(
                    "flag_without_marker",
                    UNIT_FLAG,
                    f"{row['isolate_id']}:{flag}",
                    flag,
                    f"{flag}=1 requires a marker susceptibility result",
                    f"{flag}=1 without marker for {row['organism']}",
                    "marker antibiotic tested",
                    Severity.WARNING,
                    isolate_id=row["isolate_id"],
                    organism=row["organism"],
                    flag=flag,
                    marker_codes=list(markers.get(flag, ())),
                )
            )
    return deviations


def _flag_susceptibility_contradictions(
    isolates: pl.DataFrame,
    susceptibility: pl.DataFrame,
    markers: dict[str, tuple[str, ...]],
) -> list[Deviation]:
    """A positive flag with a susceptible marker result."""
    deviations: list[Deviation] = []
    for flag, codes in markers.items():
        if not codes:
            continue
        flagged = isolates.filter(pl.col(flag) == 1).select("isolate_id")
        if flagged.is_empty():
            continue
        rows = susceptibility.filter(
            (pl.col("isolate_id").is_in(flagged["isolate_id"].implode()))
            & (pl.col("antibiotic_code").is_in(codes))
            & (pl.col("result") == "S")
        )
        for row in rows.iter_rows(named=True):
            deviations.append(
                _dev(
                    "flag_susceptibility_contradiction",
                    UNIT_FLAG,
                    f"{row['isolate_id']}:{flag}",
                    flag,
                    f"{flag}=1 implies {row['antibiotic_code']}=R",
                    f"{flag}=1 but {row['antibiotic_code']}=S",
                    "result must be R",
                    Severity.CRITICAL,
                    isolate_id=row["isolate_id"],
                    flag=flag,
                    antibiotic_code=row["antibiotic_code"],
                )
            )
    return deviations


def _marker_without_flag(
    isolates: pl.DataFrame,
    susceptibility: pl.DataFrame,
    markers: dict[str, tuple[str, ...]],
) -> list[Deviation]:
    """A resistant marker with a zero flag, for definitional flags only."""
    deviations: list[Deviation] = []
    for flag in DEFINITIONAL_FLAGS:
        codes = markers.get(flag, ())
        if not codes:
            continue
        unflagged = isolates.filter(pl.col(flag) == 0).select("isolate_id")
        if unflagged.is_empty():
            continue
        rows = susceptibility.filter(
            (pl.col("isolate_id").is_in(unflagged["isolate_id"].implode()))
            & (pl.col("antibiotic_code").is_in(codes))
            & (pl.col("result") == "R")
        )
        for row in rows.iter_rows(named=True):
            deviations.append(
                _dev(
                    "marker_without_flag",
                    UNIT_FLAG,
                    f"{row['isolate_id']}:{flag}",
                    flag,
                    f"{row['antibiotic_code']}=R implies {flag}=1",
                    f"{row['antibiotic_code']}=R but {flag}=0",
                    "flag must be 1",
                    Severity.CRITICAL,
                    isolate_id=row["isolate_id"],
                    flag=flag,
                    antibiotic_code=row["antibiotic_code"],
                )
            )
    return deviations


def _agent_specimen_mismatches(
    ds: Dataset, susceptibility_context: pl.DataFrame
) -> list[Deviation]:
    """An agent is only valid on the specimen it is reported for.

    This is the general form of the former urine-only rule: any agent whose
    `reported_for` is not "all" may only appear on that specimen. The rule uses
    `reported_for` from antibiotics.csv, not a curated per-drug list.
    """
    reported = ds.antibiotics.select("antibiotic_code", "reported_for").with_columns(
        pl.col("reported_for").fill_null("all")
    )
    context = susceptibility_context.select(
        "isolate_id", "antibiotic_code", "specimen"
    ).join(reported, on="antibiotic_code", how="left")
    offenders = context.filter(
        (pl.col("reported_for") != "all")
        & (pl.col("specimen") != pl.col("reported_for"))
    )
    return [
        _dev(
            "agent_specimen_mismatch",
            UNIT_SUSCEPTIBILITY,
            f"{row['isolate_id']}:{row['antibiotic_code']}",
            row["antibiotic_code"],
            f"agents reported for {row['reported_for']} only",
            f"{row['antibiotic_code']} reported for {row['specimen']}",
            f"specimen == {row['reported_for']}",
            Severity.WARNING,
            isolate_id=row["isolate_id"],
            specimen=row["specimen"],
            reported_for=row["reported_for"],
        )
        for row in offenders.iter_rows(named=True)
    ]


def _culture_isolation_mismatches(ds: Dataset) -> list[Deviation]:
    actual = ds.isolates.group_by("culture_id").len().rename({"len": "actual_n"})
    cultures = ds.cultures.join(actual, on="culture_id", how="left").with_columns(
        pl.col("actual_n").fill_null(0).cast(pl.Int32)
    )
    deviations = []

    for row in cultures.filter(
        (pl.col("result") == "negative") & (pl.col("actual_n") > 0)
    ).iter_rows(named=True):
        deviations.append(
            _dev(
                "negative_culture_with_isolates",
                UNIT_CULTURE_ISOLATES,
                row["culture_id"],
                "result",
                "negative culture has no isolates",
                f"negative with {row['actual_n']} isolates",
                "actual_n == 0",
                Severity.CRITICAL,
                culture_id=row["culture_id"],
                actual_n=row["actual_n"],
            )
        )

    for row in cultures.filter(
        (pl.col("result") == "positive") & (pl.col("actual_n") == 0)
    ).iter_rows(named=True):
        deviations.append(
            _dev(
                "positive_culture_without_isolates",
                UNIT_CULTURE,
                row["culture_id"],
                "result",
                "positive culture has >=1 isolate",
                "positive with 0 isolates",
                "actual_n >= 1",
                Severity.WARNING,
                culture_id=row["culture_id"],
            )
        )

    for row in cultures.filter(pl.col("n_isolates") != pl.col("actual_n")).iter_rows(
        named=True
    ):
        deviations.append(
            _dev(
                "n_isolates_count_mismatch",
                UNIT_CULTURE,
                row["culture_id"],
                "n_isolates",
                "declared count equals actual isolates",
                f"n_isolates={row['n_isolates']} actual={row['actual_n']}",
                "n_isolates == actual_n",
                Severity.WARNING,
                culture_id=row["culture_id"],
                declared=row["n_isolates"],
                actual=row["actual_n"],
            )
        )
    return deviations


def _orphans(ds: Dataset) -> list[Deviation]:
    deviations = []
    patient_ids = ds.patients["patient_id"]
    culture_ids = ds.cultures["culture_id"]
    isolate_ids = ds.isolates["isolate_id"]

    for row in ds.cultures.filter(
        ~pl.col("patient_id").is_in(patient_ids.implode())
    ).iter_rows(named=True):
        deviations.append(
            _dev(
                "orphan_culture",
                UNIT_CULTURE,
                row["culture_id"],
                "patient_id",
                "culture references an existing patient",
                f"unknown patient {row['patient_id']}",
                "patient_id in patients",
                Severity.CRITICAL,
                culture_id=row["culture_id"],
                patient_id=row["patient_id"],
            )
        )

    for row in ds.isolates.filter(
        ~pl.col("culture_id").is_in(culture_ids.implode())
    ).iter_rows(named=True):
        deviations.append(
            _dev(
                "orphan_isolate",
                UNIT_ISOLATE,
                row["isolate_id"],
                "culture_id",
                "isolate references an existing culture",
                f"unknown culture {row['culture_id']}",
                "culture_id in cultures",
                Severity.CRITICAL,
                isolate_id=row["isolate_id"],
                culture_id=row["culture_id"],
            )
        )

    for row in ds.susceptibility.filter(
        ~pl.col("isolate_id").is_in(isolate_ids.implode())
    ).iter_rows(named=True):
        deviations.append(
            _dev(
                "orphan_susceptibility",
                UNIT_SUSCEPTIBILITY,
                f"{row['isolate_id']}:{row['antibiotic_code']}",
                "isolate_id",
                "susceptibility references an existing isolate",
                f"unknown isolate {row['isolate_id']}",
                "isolate_id in isolates",
                Severity.CRITICAL,
                isolate_id=row["isolate_id"],
                antibiotic_code=row["antibiotic_code"],
            )
        )
    return deviations


def detect(ds: Dataset, ab_analytics: pl.DataFrame) -> list[Deviation]:
    markers = marker_codes(ds.antibiotics)
    return [
        *_flag_without_marker(ds.isolates, ds.susceptibility, markers),
        *_flag_susceptibility_contradictions(ds.isolates, ds.susceptibility, markers),
        *_marker_without_flag(ds.isolates, ds.susceptibility, markers),
        *_agent_specimen_mismatches(ds, ab_analytics),
        *_culture_isolation_mismatches(ds),
        *_orphans(ds),
        *detect_plausibility(ds),
    ]
