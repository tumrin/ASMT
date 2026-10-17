"""Pydantic response models for the OpenAPI/Swagger schema.

The API serves the structured JSON document and the analysis artifacts directly;
these models describe the documented shape without changing the payloads. Where a
value is a passthrough document rather than a stable schema, the model keeps the
known fields typed and allows the rest through.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# --- service ---------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str


class ErrorResponse(BaseModel):
    detail: str


# --- metadata --------------------------------------------------------------


class DateRange(BaseModel):
    start: str | None = None
    end: str | None = None


class Counts(BaseModel):
    patients: int
    cultures: int
    isolates: int
    susceptibility_results: int


class SummaryCounts(BaseModel):
    total: int
    by_family: dict[str, int]
    by_severity: dict[str, int]
    by_detector: dict[str, int]


class MetadataResponse(BaseModel):
    source: str
    counts: Counts
    date_range: DateRange
    as_of: str | None
    age_band_edges: list[float]
    settings: dict[str, Any]
    deviation_summary: SummaryCounts
    outlier_summary: SummaryCounts


# --- patients and wards ----------------------------------------------------


class PatientInfo(BaseModel):
    patient_id: str
    sex: str
    birth_year: int
    home_area: str


class PatientSummary(PatientInfo):
    wards: list[str]


class WardPatient(PatientInfo):
    n_cultures: int
    n_isolates: int


class WardPatientsResponse(BaseModel):
    ward_code: str
    n_patients: int
    patients: list[WardPatient]


# --- ward document (patients.<pid>.wards.<ward_code>) ----------------------


class IsolateFlags(BaseModel):
    esbl: int
    mrsa: int
    vre: int
    cpe: int


class WardCultureIsolate(BaseModel):
    isolate_id: str
    isolate_no: int
    organism: str
    quantity: str | None
    flags: IsolateFlags
    n_resistant_classes: int
    susceptibility: dict[str, str]


class WardCulture(BaseModel):
    culture_id: str
    sample_date: str
    iso_year: int
    iso_week: int
    age_years: int
    specimen: str
    result: str
    n_isolates: int
    days_since_admission: int | None
    isolates: list[WardCultureIsolate]


class PatientWardDetail(BaseModel):
    ward_code: str
    ward_fi: str | None
    ward_en: str | None
    ward_type: str | None
    institution: str | None
    cultures: list[WardCulture]


class PatientWardResponse(BaseModel):
    patient: PatientInfo
    ward: PatientWardDetail


# --- ward summary ----------------------------------------------------------


class AntibioticRate(BaseModel):
    antibiotic: str
    antibiotic_code: str
    antibiotic_class: str = Field(alias="class")
    specimen: str
    reported_for: str
    role: str
    n: int
    n_pos: int
    rate: float
    ci_low: float
    ci_high: float


class FlagRate(BaseModel):
    n: int
    n_pos: int
    rate: float
    marker_antibiotic_codes: list[str]


class WardOrganism(BaseModel):
    organism: str
    isolates: int
    share: float


class WardSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    ward_code: str
    ward_fi: str | None
    ward_en: str | None
    ward_type: str | None
    institution: str | None
    date_range: DateRange
    counts: Counts
    cultures_by_specimen: dict[str, int]
    cultures_by_result: dict[str, int]
    organisms: list[WardOrganism]
    flag_rates_by_organism: dict[str, dict[str, FlagRate]]
    resistance_by_antibiotic: dict[str, list[AntibioticRate]]
    antibiogram: dict[str, dict[str, list[AntibioticRate]]]
    basis: str
    as_of: str | None = None


class AntibiogramResponse(BaseModel):
    ward_code: str
    ward_type: str | None
    institution: str | None
    as_of: str | None
    specimens: dict[str, dict[str, list[AntibioticRate]]]


# --- history ---------------------------------------------------------------


class HistoryEntry(BaseModel):
    isolate_id: str
    culture_id: str
    organism: str
    specimen: str
    ward_code: str | None
    sample_date: str | None
    days_ago: int | None
    flags: IsolateFlags
    susceptibility: dict[str, str]


class HistoryResponse(BaseModel):
    patient_id: str
    organism: str | None
    history: list[HistoryEntry]


# --- antibiotics -----------------------------------------------------------


class AntibioticInfo(BaseModel):
    antibiotic: str
    antibiotic_code: str
    antibiotic_class: str = Field(alias="class")
    reported_for: str
    role: str
    marker_flags: list[str]


class AntibioticsResponse(BaseModel):
    antibiotics: list[AntibioticInfo]


# --- observed-resistance tiers ---------------------------------------------


class TierOption(BaseModel):
    antibiotic: str
    antibiotic_code: str
    antibiotic_class: str = Field(alias="class")
    reported_for: str
    role: str
    observed_resistance: float | None
    observed_n: int
    observed_ci_low: float | None
    observed_ci_high: float | None
    observed_source: str
    overall_resistance: float | None
    overall_n: int
    overall_ci_low: float | None
    overall_ci_high: float | None


class TierListResponse(BaseModel):
    """`/tiers/{organism}?specimen=...` — one observed rate list."""

    model_config = ConfigDict(extra="forbid")

    organism: str
    specimen: str
    context: dict[str, Any]
    tiers: list[TierOption]


class TierMapResponse(BaseModel):
    """`/tiers/{organism}` without a specimen — every specimen's rate list."""

    model_config = ConfigDict(extra="forbid")

    organism: str
    tiers: dict[str, list[TierOption]]


# --- decision briefs -------------------------------------------------------


class Warning(BaseModel):
    code: str
    severity: str
    message: str


class DecisionOption(TierOption):
    prior_result: str | None
    prior_resistant: bool
    prior_susceptible: bool
    warnings: list[Warning]
    rank: int
    rank_group: int


class ScreenResult(BaseModel):
    antibiotic: str
    antibiotic_code: str
    result: str
    interpretation: str


class Exclusion(BaseModel):
    antibiotic: str
    antibiotic_code: str
    reason: str
    detail: str


class Period(BaseModel):
    start: str | None = None
    end: str | None = None


class DecisionBriefResponse(BaseModel):
    request_id: str
    generated_at: str
    data_as_of: str | None
    headline: str
    context: dict[str, Any]
    period: Period
    options: list[DecisionOption]
    screens: list[ScreenResult]
    excluded: list[Exclusion]
    patient_history: list[HistoryEntry]
    limitations: list[str]


# --- data quality logs -----------------------------------------------------


class DeviationRecord(BaseModel):
    family: str
    detector: str
    unit_type: str
    unit_key: str
    metric: str | None
    expected: str | None
    observed: str | None
    threshold: str | None
    severity: str
    detail: dict[str, Any]


class DeviationsResponse(BaseModel):
    n: int
    deviations: list[DeviationRecord]


class OutliersResponse(BaseModel):
    n: int
    outliers: list[DeviationRecord]
