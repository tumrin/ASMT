from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl
from fastapi import FastAPI, HTTPException, Query
from fastapi import Path as PathParam
from resistance_core.antibiotic_properties import metadata_by_code, properties_payload

from .responses import (
    AntibiogramResponse,
    AntibioticsResponse,
    DeviationsResponse,
    ErrorResponse,
    HealthResponse,
    HistoryResponse,
    MetadataResponse,
    OutliersResponse,
    PatientsResponse,
    PatientSummary,
    PatientWardResponse,
    RecommendationsResponse,
    WardPatientsResponse,
    WardSummary,
)

EXCLUSION_NOT_REPORTED_FOR_SPECIMEN = "not_reported_for_specimen"
EXCLUSION_NO_SPECIMEN_DATA = "no_specimen_data"

LIMITATIONS = [
    "In-vitro susceptibility only; the dataset has no outcome, dose, allergy or renal data.",
    "Specimen is not a diagnosis.",
    (
        "Rates count the first isolate per patient x species x specimen per period and "
        "are only reported at or above the configured minimum count."
    ),
    "A patient's own earlier results are history only and do not change a recommendation.",
    "This is decision support, not a prescription.",
]

DESCRIPTION = """\
Cumulative antibiogram over the synthetic microbiology dataset. Every value is
either read from the dataset or derived arithmetically from it; the API adds no
clinical thresholds beyond the configurable reporting floor and traffic-light
cutoffs.

The antibiogram is the susceptibility matrix per scope (hospital, inpatient ward
or outpatient region) and period (calendar year or the last four weeks). The
recommendation endpoint ranks agents by cumulative susceptibility. Findings in
the deviation and outlier logs are reported only and never applied to the data.

This is an unauthenticated local exploration service: there is no
authentication, authorisation or pagination.

**Limitations**

- In-vitro susceptibility only; the dataset has no outcome, dose, allergy or
  renal data.
- Specimen is not a diagnosis.
- A patient's own earlier results are history only.
- Decision support, not a prescription.
"""

OPENAPI_TAGS = [
    {"name": "Service", "description": "Liveness and document metadata."},
    {"name": "Patients", "description": "Patient summaries and culture histories."},
    {"name": "Wards", "description": "Ward summaries and patient rosters."},
    {
        "name": "Antibiogram",
        "description": "The cumulative susceptibility matrix per scope and period.",
    },
    {
        "name": "Recommendations",
        "description": "Empiric antibiotic ranking; decision support, not a prescription.",
    },
    {
        "name": "Data quality",
        "description": "Reported consistency deviations and statistical outliers.",
    },
]


def _read_log(path: Path) -> list[dict[str, Any]]:
    rows = pl.read_csv(path).to_dicts()
    for row in rows:
        detail = row.get("detail")
        if isinstance(detail, str):
            try:
                row["detail"] = json.loads(detail)
            except json.JSONDecodeError:
                pass
    return rows


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _patient_cultures(doc: dict[str, Any], patient_id: str) -> list[dict[str, Any]]:
    patient = doc.get("patients", {}).get(patient_id)
    if patient is None:
        return []
    cultures: list[dict[str, Any]] = []
    for ward in patient.get("wards", {}).values():
        for culture in ward.get("cultures", []):
            cultures.append({**culture, "ward_code": ward.get("ward_code")})
    return cultures


def _patient_history(
    doc: dict[str, Any],
    patient_id: str,
    organism: str | None,
    as_of: date | None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for culture in _patient_cultures(doc, patient_id):
        sampled = _parse_date(culture.get("sample_date"))
        for isolate in culture.get("isolates", []):
            if organism and isolate.get("organism") != organism:
                continue
            rows.append(
                {
                    "isolate_id": isolate.get("isolate_id"),
                    "culture_id": culture.get("culture_id"),
                    "organism": isolate.get("organism"),
                    "specimen": culture.get("specimen"),
                    "ward_code": culture.get("ward_code"),
                    "sample_date": culture.get("sample_date"),
                    "days_ago": (as_of - sampled).days if as_of and sampled else None,
                    "flags": isolate.get("flags", {}),
                    "susceptibility": isolate.get("susceptibility", {}),
                }
            )
    rows.sort(key=lambda row: (row["sample_date"] or "", row["isolate_id"] or ""))
    rows.reverse()
    return rows[:limit]


def _default_period(periods: list[str]) -> str:
    annual = [period for period in periods if period.startswith("annual:")]
    if annual:
        return annual[-1]
    return periods[-1] if periods else "last4w"


def _fallback_chain(
    scope: str, unit: str, base_period: str, annual_period: str
) -> list[str]:
    keys = [f"{scope}|{unit}|{base_period}"]
    if annual_period != base_period:
        keys.append(f"{scope}|{unit}|{annual_period}")
    if scope != "hospital" or unit != "-":
        keys.append(f"hospital|-|{base_period}")
        if annual_period != base_period:
            keys.append(f"hospital|-|{annual_period}")
    chain: list[str] = []
    for key in keys:
        if key not in chain:
            chain.append(key)
    return chain


def _select_cell(
    cells: list[tuple[str, dict[str, Any]]], min_isolates: int
) -> tuple[str, dict[str, Any]]:
    for key, entry in cells:
        if int(entry["n"]) >= min_isolates:
            return key, entry
    return cells[0]


def create_app(
    dataset_path: str | Path,
    deviations_path: str | Path | None = None,
    outliers_path: str | Path | None = None,
) -> FastAPI:
    dataset_path = Path(dataset_path)
    deviations_path = Path(deviations_path) if deviations_path else None
    outliers_path = Path(outliers_path) if outliers_path else None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not dataset_path.exists():
            raise FileNotFoundError(f"dataset.json not found: {dataset_path}")
        doc = json.loads(dataset_path.read_text(encoding="utf-8"))
        app.state.doc = doc
        app.state.antibiotics = pl.DataFrame(doc["antibiotics"])
        app.state.antibiotic_metadata = metadata_by_code(app.state.antibiotics)
        app.state.data_as_of = _parse_date(doc.get("metadata", {}).get("data_as_of"))

        if deviations_path and deviations_path.exists():
            app.state.deviations = _read_log(deviations_path)
        else:
            app.state.deviations = []

        if outliers_path and outliers_path.exists():
            app.state.outliers = _read_log(outliers_path)
        else:
            app.state.outliers = []
        yield

    app = FastAPI(
        title="Cumulative antibiogram",
        summary="Susceptibility rates, antibiogram and empiric recommendations",
        description=DESCRIPTION,
        version="0.2.0",
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )

    @app.get(
        "/health",
        tags=["Service"],
        summary="Liveness check",
        response_model=HealthResponse,
    )
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(
        "/metadata",
        tags=["Service"],
        summary="Document metadata",
        description="Counts, date range, settings, available scopes and periods.",
        response_model=MetadataResponse,
    )
    def metadata() -> dict[str, object]:
        return app.state.doc["metadata"]

    @app.get(
        "/patients",
        tags=["Patients"],
        summary="Patient list",
        description="Every patient with the wards they have a culture in.",
        response_model=PatientsResponse,
    )
    def list_patients() -> dict[str, object]:
        rows = [
            {
                "patient_id": patient["patient_id"],
                "sex": patient["sex"],
                "birth_year": patient["birth_year"],
                "home_area": patient["home_area"],
                "wards": sorted(patient["wards"].keys()),
            }
            for patient in app.state.doc["patients"].values()
        ]
        rows.sort(key=lambda row: row["patient_id"])
        return {"n": len(rows), "patients": rows}

    @app.get(
        "/patients/{patient_id}",
        tags=["Patients"],
        summary="Patient summary",
        description="Demographics and the wards the patient has a culture in.",
        response_model=PatientSummary,
        responses={404: {"model": ErrorResponse, "description": "Unknown patient"}},
    )
    def get_patient(
        patient_id: str = PathParam(description="Patient identifier, e.g. `P001`."),
    ) -> dict[str, object]:
        patient = app.state.doc["patients"].get(patient_id)
        if patient is None:
            raise HTTPException(status_code=404, detail=f"unknown patient {patient_id}")
        return {
            "patient_id": patient["patient_id"],
            "sex": patient["sex"],
            "birth_year": patient["birth_year"],
            "home_area": patient["home_area"],
            "wards": sorted(patient["wards"].keys()),
        }

    @app.get(
        "/patients/{patient_id}/wards/{ward_code}",
        tags=["Patients"],
        summary="Patient ward document",
        description="One patient x one ward, including every culture and isolate.",
        response_model=PatientWardResponse,
        responses={
            404: {"model": ErrorResponse, "description": "Unknown patient or ward link"}
        },
    )
    def get_patient_ward(
        patient_id: str = PathParam(description="Patient identifier."),
        ward_code: str = PathParam(description="Ward identifier."),
    ) -> dict[str, object]:
        patient = app.state.doc["patients"].get(patient_id)
        if patient is None:
            raise HTTPException(status_code=404, detail=f"unknown patient {patient_id}")
        ward = patient["wards"].get(ward_code)
        if ward is None:
            raise HTTPException(
                status_code=404, detail=f"patient {patient_id} has no ward {ward_code}"
            )
        return {
            "patient": {
                "patient_id": patient["patient_id"],
                "sex": patient["sex"],
                "birth_year": patient["birth_year"],
                "home_area": patient["home_area"],
            },
            "ward": ward,
        }

    @app.get(
        "/patients/{patient_id}/history",
        tags=["Patients"],
        summary="Patient isolate history",
        description=(
            "Prior isolates of the patient, most recent first. History only; it does "
            "not change any recommendation. With an organism, only that organism is "
            "returned."
        ),
        response_model=HistoryResponse,
        responses={404: {"model": ErrorResponse, "description": "Unknown patient"}},
    )
    def get_patient_history(
        patient_id: str = PathParam(description="Patient identifier."),
        organism: str | None = Query(
            default=None, description="Restrict to one organism."
        ),
    ) -> dict[str, object]:
        if patient_id not in app.state.doc.get("patients", {}):
            raise HTTPException(status_code=404, detail=f"unknown patient {patient_id}")
        history = _patient_history(
            app.state.doc, patient_id, organism, app.state.data_as_of
        )
        return {"patient_id": patient_id, "organism": organism, "history": history}

    @app.get(
        "/wards/{ward_code}",
        tags=["Wards"],
        summary="Ward summary",
        description="Volumes, case mix, top organisms and per-organism flag rates.",
        response_model=WardSummary,
        responses={404: {"model": ErrorResponse, "description": "Unknown ward"}},
    )
    def get_ward(
        ward_code: str = PathParam(description="Ward identifier."),
    ) -> dict[str, object]:
        ward = app.state.doc.get("wards", {}).get(ward_code)
        if ward is None:
            raise HTTPException(status_code=404, detail=f"unknown ward {ward_code}")
        return {
            **ward,
            "data_as_of": str(app.state.data_as_of) if app.state.data_as_of else None,
        }

    @app.get(
        "/wards/{ward_code}/patients",
        tags=["Wards"],
        summary="Patients in a ward",
        description="Patients with a culture in the ward, with culture and isolate counts.",
        response_model=WardPatientsResponse,
    )
    def get_ward_patients(
        ward_code: str = PathParam(description="Ward identifier."),
    ) -> dict[str, object]:
        rows = []
        for patient in app.state.doc["patients"].values():
            ward = patient["wards"].get(ward_code)
            if ward is None:
                continue
            rows.append(
                {
                    "patient_id": patient["patient_id"],
                    "sex": patient["sex"],
                    "birth_year": patient["birth_year"],
                    "home_area": patient["home_area"],
                    "n_cultures": len(ward["cultures"]),
                    "n_isolates": sum(
                        len(culture["isolates"]) for culture in ward["cultures"]
                    ),
                }
            )
        rows.sort(key=lambda row: row["patient_id"])
        return {"ward_code": ward_code, "n_patients": len(rows), "patients": rows}

    @app.get(
        "/antibiotics",
        tags=["Antibiogram"],
        summary="Antibiotic metadata",
        description=(
            "Metadata derived from antibiotics.csv: class, reported_for, derived "
            "role (screen/therapeutic) and marker flags."
        ),
        response_model=AntibioticsResponse,
    )
    def get_antibiotics() -> dict[str, object]:
        return properties_payload(app.state.antibiotics)

    @app.get(
        "/antibiogram",
        tags=["Antibiogram"],
        summary="Cumulative susceptibility matrix",
        description=(
            "The (organism, specimen) x antibiotic matrix for one scope and period. "
            "Screens are excluded unless `include_screens=true`."
        ),
        response_model=AntibiogramResponse,
        responses={
            404: {
                "model": ErrorResponse,
                "description": "No data for that scope/period",
            }
        },
    )
    def get_antibiogram(
        scope: str = Query(
            default="hospital",
            description="`hospital`, `ward` (inpatient) or `region` (outpatient).",
        ),
        unit: str = Query(
            default="-", description="Ward code or home area; `-` for hospital."
        ),
        period: str | None = Query(
            default=None,
            description="`annual:<year>` or `last4w`; defaults to the latest year.",
        ),
        organism: str | None = Query(
            default=None, description="Restrict to one organism."
        ),
        specimen: str | None = Query(
            default=None, description="Restrict to one specimen."
        ),
        include_screens: bool = Query(
            default=False, description="Include screen agents (e.g. cefoxitin)."
        ),
    ) -> dict[str, object]:
        doc = app.state.doc
        metadata = doc.get("metadata", {})
        if period is None:
            period = _default_period(metadata.get("periods", []))
        rows = doc.get("antibiogram", {}).get(f"{scope}|{unit}|{period}")
        if rows is None:
            raise HTTPException(
                status_code=404,
                detail=f"no antibiogram for scope={scope} unit={unit} period={period}",
            )
        organisms: list[dict[str, Any]] = []
        for organism_key, entries in rows.items():
            organism_name, specimen_name = organism_key.split("|", 1)
            if organism and organism_name != organism:
                continue
            if specimen and specimen_name != specimen:
                continue
            cells = [
                entry
                for entry in entries
                if include_screens or entry["role"] != "screen"
            ]
            if not cells:
                continue
            organisms.append(
                {
                    "organism": organism_name,
                    "specimen": specimen_name,
                    "antibiotics": cells,
                }
            )
        organisms.sort(key=lambda row: (row["organism"], row["specimen"]))
        return {
            "scope": scope,
            "unit": unit,
            "period": period,
            "data_as_of": metadata.get("data_as_of"),
            "organisms": organisms,
        }

    @app.get(
        "/recommendations",
        tags=["Recommendations"],
        summary="Empiric antibiotic ranking",
        description=(
            "Agents for a known organism and specimen, ranked by cumulative "
            "susceptibility. Cells below the minimum count fall back from last4w to "
            "annual and then to hospital scope; each option reports the scope and "
            "period its rate came from. Decision support, not a prescription."
        ),
        response_model=RecommendationsResponse,
    )
    def get_recommendation(
        scope: str = Query(
            default="hospital",
            description="`hospital`, `ward` (inpatient) or `region` (outpatient).",
        ),
        unit: str = Query(
            default="-", description="Ward code or home area; `-` for hospital."
        ),
        organism: str = Query(
            description="Organism name as it appears in the dataset."
        ),
        specimen: str = Query(description="Specimen the isolate was grown from."),
        period: str | None = Query(
            default=None,
            description="Starting period, e.g. `last4w` (default) or `annual:2024`.",
        ),
    ) -> dict[str, object]:
        doc = app.state.doc
        metadata = doc.get("metadata", {})
        matrix = doc.get("antibiogram", {})
        periods = metadata.get("periods", [])
        min_isolates = int(metadata.get("settings", {}).get("min_isolates", 30))

        base_period = period or "last4w"
        annual_period = (
            _default_period(periods) if base_period == "last4w" else base_period
        )
        chain = _fallback_chain(scope, unit, base_period, annual_period)

        organism_key = f"{organism}|{specimen}"
        candidates: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for key in chain:
            for entry in matrix.get(key, {}).get(organism_key, []):
                if entry["role"] == "screen":
                    continue
                candidates.setdefault(entry["antibiotic"], []).append((key, entry))

        options: list[dict[str, Any]] = []
        for cells in candidates.values():
            key, selected = _select_cell(cells, min_isolates)
            source_scope, source_unit, source_period = key.split("|", 2)
            options.append(
                {
                    **selected,
                    "source_scope": source_scope,
                    "source_unit": source_unit,
                    "source_period": source_period,
                }
            )
        options.sort(
            key=lambda entry: (
                entry["susceptibility_rate"] is None,
                -(entry["susceptibility_rate"] or 0.0),
                entry["antibiotic"],
            )
        )

        excluded: list[dict[str, str]] = []
        for row in doc.get("antibiotics", []):
            if row.get("role") == "screen":
                continue
            name = row["antibiotic"]
            if name in candidates:
                continue
            reported_for = row.get("reported_for") or "all"
            if reported_for not in ("all", specimen):
                reason = EXCLUSION_NOT_REPORTED_FOR_SPECIMEN
                detail = f"{name} is not reported for {specimen} specimens."
            else:
                reason = EXCLUSION_NO_SPECIMEN_DATA
                detail = f"No {specimen} susceptibility data for {organism}."
            excluded.append(
                {
                    "antibiotic": name,
                    "antibiotic_code": row["antibiotic_code"],
                    "reason": reason,
                    "detail": detail,
                }
            )
        excluded.sort(key=lambda entry: (entry["reason"], entry["antibiotic"]))

        return {
            "scope": scope,
            "unit": unit,
            "organism": organism,
            "specimen": specimen,
            "data_as_of": metadata.get("data_as_of"),
            "options": options,
            "excluded": excluded,
            "limitations": LIMITATIONS,
        }

    @app.get(
        "/deviations",
        tags=["Data quality"],
        summary="Consistency deviation log",
        description=(
            "Rule-based findings, reported only. `detail` is a JSON object; "
            "findings are never applied to the data."
        ),
        response_model=DeviationsResponse,
    )
    def get_deviations(
        family: str | None = Query(
            default=None, description="`consistency` or `statistical`."
        ),
        severity: str | None = Query(
            default=None, description="`info`, `warning` or `critical`."
        ),
        detector: str | None = Query(
            default=None, description="Detector name, e.g. `orphan_isolate`."
        ),
    ) -> dict[str, object]:
        rows = app.state.deviations
        if family:
            rows = [row for row in rows if row["family"] == family]
        if severity:
            rows = [row for row in rows if row["severity"] == severity]
        if detector:
            rows = [row for row in rows if row["detector"] == detector]
        return {"n": len(rows), "deviations": rows}

    @app.get(
        "/outliers",
        tags=["Data quality"],
        summary="Statistical outlier log",
        description=(
            "Funnel-plot outliers, reported only. Filtering on the cell fields "
            "reads `detail`; `min_n` is a consumer-side filter, not a cutoff."
        ),
        response_model=OutliersResponse,
    )
    def get_outliers(
        detector: str | None = Query(
            default=None, description="`ward_rate_outlier` or `weekly_rate_outlier`."
        ),
        severity: str | None = Query(
            default=None, description="`info`, `warning` or `critical`."
        ),
        organism: str | None = Query(default=None, description="Cell organism."),
        antibiotic: str | None = Query(default=None, description="Cell antibiotic."),
        specimen: str | None = Query(default=None, description="Cell specimen."),
        ward_code: str | None = Query(default=None, description="Cell ward."),
        week: str | None = Query(
            default=None, description="Cell ISO year/week for weekly outliers."
        ),
        min_n: int | None = Query(
            default=None, description="Minimum cell `n`; consumer-side filter."
        ),
    ) -> dict[str, object]:
        def matches(row: dict[str, Any]) -> bool:
            detail = row.get("detail") or {}
            if detector and row["detector"] != detector:
                return False
            if severity and row["severity"] != severity:
                return False
            if organism and detail.get("organism") != organism:
                return False
            if antibiotic and detail.get("antibiotic") != antibiotic:
                return False
            if specimen and detail.get("specimen") != specimen:
                return False
            if ward_code and detail.get("ward_code") != ward_code:
                return False
            if week and detail.get("week") != week:
                return False
            return min_n is None or int(detail.get("n", 0)) >= min_n

        rows = [row for row in app.state.outliers if matches(row)]
        return {"n": len(rows), "outliers": rows}

    return app
