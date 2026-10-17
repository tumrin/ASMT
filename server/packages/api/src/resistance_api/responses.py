"""Pydantic response models for the OpenAPI/Swagger schema.

The API serves the structured JSON document and the analysis artifacts directly;
these models describe the documented shape without changing the payloads. Where a
value is a passthrough document rather than a stable schema, the model keeps the
known fields typed and allows the rest through.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

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


class ScopeUnit(BaseModel):
    unit: str
    label: str


class MetadataResponse(BaseModel):
    source: str
    counts: Counts
    date_range: DateRange
    data_as_of: str | None
    age_band_edges: list[float]
    settings: dict[str, Any]
    scopes: dict[str, list[ScopeUnit]]
    periods: list[str]
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


class PatientListEntry(PatientInfo):
    wards: list[str]


class PatientsResponse(BaseModel):
    n: int
    patients: list[PatientListEntry]


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
    basis: str
    data_as_of: str | None = None


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


# --- antibiogram -----------------------------------------------------------


class AntibioticCell(BaseModel):
    antibiotic: str
    antibiotic_code: str
    antibiotic_class: str = Field(alias="class")
    reported_for: str
    role: str
    n: int
    n_s: int
    susceptibility_rate: float | None
    ci_low: float | None
    ci_high: float | None
    traffic_light: str


class AntibiogramRow(BaseModel):
    organism: str
    specimen: str
    antibiotics: list[AntibioticCell]


class AntibiogramResponse(BaseModel):
    scope: str
    unit: str
    period: str
    data_as_of: str | None
    organisms: list[AntibiogramRow]


# --- recommendations -------------------------------------------------------


class RecommendationOption(AntibioticCell):
    source_scope: str
    source_unit: str
    source_period: str


class Exclusion(BaseModel):
    antibiotic: str
    antibiotic_code: str
    reason: str
    detail: str


class RecommendationsResponse(BaseModel):
    scope: str
    unit: str
    organism: str
    specimen: str
    data_as_of: str | None
    options: list[RecommendationOption]
    excluded: list[Exclusion]
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
