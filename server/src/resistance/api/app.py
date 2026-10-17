from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi import Path as PathParam

from .responses import (
    AntibiogramResponse,
    AntibioticsResponse,
    ErrorResponse,
    HealthResponse,
    HistoryResponse,
    MetadataResponse,
    PatientsResponse,
    PatientSummary,
    PatientWardResponse,
    RecommendationsResponse,
    WardPatientsResponse,
    WardSummary,
)

EXCLUSION_NOT_REPORTED_FOR_SPECIMEN = "not_reported_for_specimen"
EXCLUSION_NO_SPECIMEN_DATA = "no_specimen_data"

# Inpatient onset scopes resolve to the whole-ward rate when their own cell is below
# the reporting floor, then to hospital (analysis: antibiogram.py, spec §6.4).
ONSET_SCOPES = ("ward-early", "ward-late")

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

The antibiogram is the susceptibility matrix per scope (hospital, inpatient ward,
inpatient onset sub-scope or outpatient region) and period (calendar year or the
last four weeks). The recommendation endpoint ranks agents by cumulative
susceptibility.

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
]


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


def _patient_ward_pairs(
    doc: dict[str, Any], ward_code: str
) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    for patient in doc.get("patients", {}).values():
        ward = patient.get("wards", {}).get(ward_code)
        if ward is not None:
            yield patient, ward


def _ward_counts(doc: dict[str, Any], ward_code: str) -> dict[str, int]:
    pairs = list(_patient_ward_pairs(doc, ward_code))
    return {
        "patients": len(pairs),
        "cultures": sum(len(ward["cultures"]) for _, ward in pairs),
        "isolates": sum(
            len(culture["isolates"])
            for _, ward in pairs
            for culture in ward["cultures"]
        ),
    }


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
    if scope in ONSET_SCOPES:
        keys.append(f"ward|{unit}|{base_period}")
        if annual_period != base_period:
            keys.append(f"ward|{unit}|{annual_period}")
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


def create_app(dataset_path: str | Path) -> FastAPI:
    dataset_path = Path(dataset_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not dataset_path.exists():
            raise FileNotFoundError(f"dataset.json not found: {dataset_path}")
        doc = json.loads(dataset_path.read_text(encoding="utf-8"))
        app.state.doc = doc
        app.state.data_as_of = _parse_date(doc.get("metadata", {}).get("data_as_of"))
        yield

    app = FastAPI(
        title="Cumulative antibiogram",
        summary="Susceptibility rates, antibiogram and empiric recommendations",
        description=DESCRIPTION,
        version="0.3.0",
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
        description="Ward metadata and culture/isolate counts.",
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
            "counts": _ward_counts(app.state.doc, ward_code),
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
        rows = [
            {
                "patient_id": patient["patient_id"],
                "sex": patient["sex"],
                "birth_year": patient["birth_year"],
                "home_area": patient["home_area"],
                "n_cultures": len(ward["cultures"]),
                "n_isolates": sum(len(c["isolates"]) for c in ward["cultures"]),
            }
            for patient, ward in _patient_ward_pairs(app.state.doc, ward_code)
        ]
        rows.sort(key=lambda row: row["patient_id"])
        return {"ward_code": ward_code, "n_patients": len(rows), "patients": rows}

    @app.get(
        "/antibiotics",
        tags=["Antibiogram"],
        summary="Antibiotic metadata",
        description=(
            "Metadata derived from antibiotics.csv: class, reported_for and derived "
            "role (screen/therapeutic)."
        ),
        response_model=AntibioticsResponse,
    )
    def get_antibiotics() -> dict[str, object]:
        return {"antibiotics": app.state.doc["antibiotics"]}

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
            description=(
                "`hospital`, `ward` (inpatient), `ward-early` / `ward-late` "
                "(inpatient by onset) or `region` (outpatient)."
            ),
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
            "annual and then to hospital scope; an onset scope falls back to its ward "
            "first. Each option reports the scope and period its rate came from. "
            "Decision support, not a prescription."
        ),
        response_model=RecommendationsResponse,
    )
    def get_recommendation(
        scope: str = Query(
            default="hospital",
            description=(
                "`hospital`, `ward` (inpatient), `ward-early` / `ward-late` "
                "(inpatient by onset) or `region` (outpatient)."
            ),
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
        days_since_admission: int | None = Query(
            default=None,
            description=(
                "Days since admission for an inpatient; with scope `ward` it selects "
                "the onset sub-scope (`ward-early` below `hospital_onset_days`, "
                "`ward-late` at or above)."
            ),
        ),
    ) -> dict[str, object]:
        doc = app.state.doc
        metadata = doc.get("metadata", {})
        matrix = doc.get("antibiogram", {})
        periods = metadata.get("periods", [])
        settings = metadata.get("settings", {})
        min_isolates = int(settings.get("min_isolates", 30))
        onset_days = int(settings.get("hospital_onset_days", 3))

        if scope == "ward" and days_since_admission is not None:
            scope = "ward-early" if days_since_admission < onset_days else "ward-late"

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

    return app
