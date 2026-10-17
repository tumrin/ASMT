from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import polars as pl
from fastapi import FastAPI, HTTPException, Query
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict, Field
from resistance_core.antibiotic_properties import (
    AntibioticMetadata,
    metadata_by_code,
    properties_payload,
)
from resistance_core.decision import (
    EXCLUSION_NO_SPECIMEN_DATA,
    EXCLUSION_NOT_REPORTED_FOR_SPECIMEN,
    rank_options,
    warnings_for,
)
from resistance_core.tiers import TierModel

from .responses import (
    AntibiogramResponse,
    AntibioticsResponse,
    DecisionBriefResponse,
    DeviationsResponse,
    ErrorResponse,
    HealthResponse,
    HistoryResponse,
    MetadataResponse,
    OutliersResponse,
    PatientSummary,
    PatientWardResponse,
    TierListResponse,
    TierMapResponse,
    WardPatientsResponse,
    WardSummary,
)

LIMITATIONS = [
    "In-vitro susceptibility only; the dataset has no outcome, dose, allergy or renal data.",
    "Specimen is not a diagnosis.",
    "Rates use the first-isolate surveillance view and the marker antibiotic denominators in susceptibility.csv.",
    "No clinical thresholds, routes, spectrum or indications are used; they are not in the dataset.",
]

DESCRIPTION = """\
Directed, ward-aware in-vitro susceptibility evidence over the synthetic
microbiology dataset. Every value is either read from the dataset or derived
arithmetically from it; the API adds no clinical thresholds.

The evidence endpoints recompute observed resistance from the analysis
artifacts, while the document endpoints serve `dataset.json` directly. Findings
in the deviation and outlier logs are reported only and never applied to the
data.

This is an unauthenticated local exploration service: there is no
authentication, authorisation or pagination.

**Limitations**

- In-vitro susceptibility only; the dataset has no outcome, dose, allergy or
  renal data.
- Specimen is not a diagnosis.
- Rates use the first-isolate surveillance view and the marker antibiotic
  denominators in `susceptibility.csv`.
- No clinical thresholds, routes, spectrum or indications are used; they are
  not in the dataset.
"""

OPENAPI_TAGS = [
    {"name": "Service", "description": "Liveness and document metadata."},
    {"name": "Patients", "description": "Patient summaries and ward histories."},
    {"name": "Wards", "description": "Ward summaries and patient rosters."},
    {
        "name": "Evidence",
        "description": "Observed in-vitro resistance rates, per ward and by organism.",
    },
    {
        "name": "Decisions",
        "description": "Directed decision briefs; a susceptibility list, not a prescription.",
    },
    {
        "name": "Data quality",
        "description": "Reported consistency deviations and statistical outliers.",
    },
]


class EncounterIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"ward_code": "ICU", "admission_date": "2024-01-01"}
        }
    )

    ward_code: str = Field(description="Ward the encounter takes place in.")
    admission_date: str | None = Field(
        default=None, description="ISO admission date, when known."
    )


class CultureIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "organism": "Escherichia coli",
                "specimen": "urine",
                "culture_date": "2024-01-05",
            }
        }
    )

    organism: str = Field(description="Organism name as it appears in the dataset.")
    specimen: str = Field(description="Specimen the isolate was grown from.")
    culture_date: str | None = Field(
        default=None, description="ISO sample date; disambiguates repeat cultures."
    )
    culture_id: str | None = Field(
        default=None, description="Exact culture to anchor the brief on, when known."
    )


class DecisionBriefRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "patient_id": "P1",
                "encounter": {"ward_code": "ICU", "admission_date": "2024-01-01"},
                "culture": {
                    "organism": "Escherichia coli",
                    "specimen": "urine",
                    "culture_date": "2024-01-05",
                },
            }
        }
    )

    patient_id: str = Field(description="Patient the brief is for.")
    encounter: EncounterIn = Field(description="Where the patient is being treated.")
    culture: CultureIn = Field(description="The directed isolate.")


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


def _ward_meta(doc: dict[str, Any], ward_code: str | None) -> dict[str, Any] | None:
    if not ward_code:
        return None
    return doc.get("wards", {}).get(ward_code)


def _context(doc: dict[str, Any], ward_code: str | None) -> dict[str, Any]:
    context: dict[str, Any] = {}
    ward = _ward_meta(doc, ward_code)
    if ward:
        context["ward_code"] = ward_code
        if ward.get("ward_type"):
            context["ward_type"] = ward["ward_type"]
        if ward.get("institution"):
            context["institution"] = ward["institution"]
    return context


def _patient_cultures(doc: dict[str, Any], patient_id: str) -> list[dict[str, Any]]:
    patient = doc.get("patients", {}).get(patient_id)
    if patient is None:
        return []
    cultures: list[dict[str, Any]] = []
    for ward in patient.get("wards", {}).values():
        for culture in ward.get("cultures", []):
            cultures.append({**culture, "ward_code": ward.get("ward_code")})
    return cultures


def _find_isolate(
    doc: dict[str, Any],
    patient_id: str,
    *,
    ward_code: str | None,
    specimen: str,
    organism: str,
    culture_id: str | None = None,
    culture_date: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for culture in _patient_cultures(doc, patient_id):
        if culture_id and culture.get("culture_id") != culture_id:
            continue
        if culture.get("specimen") != specimen:
            continue
        if culture_date and culture.get("sample_date") != culture_date:
            continue
        if ward_code and culture.get("ward_code") != ward_code:
            continue
        for isolate in culture.get("isolates", []):
            if isolate.get("organism") == organism:
                candidates.append((culture, isolate))
    if candidates:
        return candidates[-1]
    for culture in reversed(_patient_cultures(doc, patient_id)):
        if culture.get("specimen") != specimen:
            continue
        for isolate in culture.get("isolates", []):
            if isolate.get("organism") == organism:
                return culture, isolate
    return None


def _patient_history(
    doc: dict[str, Any],
    patient_id: str,
    organism: str | None,
    as_of: date | None,
    before: date | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for culture in _patient_cultures(doc, patient_id):
        sampled = _parse_date(culture.get("sample_date"))
        if before is not None and sampled is not None and sampled >= before:
            continue
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


def _latest_prior(result: list[str]) -> str | None:
    return result[-1] if result else None


def _antibiogram(
    doc: dict[str, Any],
    ward_code: str,
    specimen: str | None,
    organism: str | None,
) -> dict[str, Any]:
    ward = _ward_meta(doc, ward_code) or {}
    nested = ward.get("antibiogram", {})
    if not specimen and not organism:
        return nested
    filtered: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for specimen_name, organisms in nested.items():
        if specimen and specimen_name != specimen:
            continue
        for organism_name, entries in organisms.items():
            if organism and organism_name != organism:
                continue
            filtered.setdefault(specimen_name, {})[organism_name] = entries
    return filtered


def create_app(
    dataset_path: str | Path,
    analytics_path: str | Path | None = None,
    deviations_path: str | Path | None = None,
    outliers_path: str | Path | None = None,
) -> FastAPI:
    dataset_path = Path(dataset_path)
    analytics_path = Path(analytics_path) if analytics_path else None
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
        app.state.model = None

        metadata = doc.get("metadata", {})
        app.state.as_of = _parse_date(metadata.get("as_of"))

        if analytics_path and analytics_path.exists():
            frame = pl.read_csv(analytics_path)
            app.state.model = TierModel(frame, app.state.antibiotics)

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
        title="Resistance analysis",
        summary="Ward-aware in-vitro susceptibility evidence",
        description=DESCRIPTION,
        version="0.1.0",
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
        description="Counts, date range, settings and the deviation/outlier summaries.",
        response_model=MetadataResponse,
    )
    def metadata() -> dict[str, object]:
        return app.state.doc["metadata"]

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
        "/wards/{ward_code}",
        tags=["Wards"],
        summary="Ward summary",
        description=(
            "Volumes, case mix, top organisms, per-organism flag rates, "
            "resistance by antibiotic and an organism-stratified antibiogram."
        ),
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
            "as_of": str(app.state.as_of) if app.state.as_of else None,
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
        "/wards/{ward_code}/antibiogram",
        tags=["Evidence"],
        summary="Ward antibiogram",
        description=(
            "Observed resistance per specimen and organism in the ward, from the "
            "first-isolate surveillance view. Screens are excluded."
        ),
        response_model=AntibiogramResponse,
        responses={404: {"model": ErrorResponse, "description": "Unknown ward"}},
    )
    def get_ward_antibiogram(
        ward_code: str = PathParam(description="Ward identifier."),
        specimen: str | None = Query(
            default=None, description="Restrict to one specimen."
        ),
        organism: str | None = Query(
            default=None, description="Restrict to one organism."
        ),
    ) -> dict[str, object]:
        ward = app.state.doc.get("wards", {}).get(ward_code)
        if ward is None:
            raise HTTPException(status_code=404, detail=f"unknown ward {ward_code}")
        return {
            "ward_code": ward_code,
            "ward_type": ward.get("ward_type"),
            "institution": ward.get("institution"),
            "as_of": str(app.state.as_of) if app.state.as_of else None,
            "specimens": _antibiogram(app.state.doc, ward_code, specimen, organism),
        }

    @app.get(
        "/patients/{patient_id}/history",
        tags=["Evidence"],
        summary="Patient isolate history",
        description=(
            "Prior isolates of the patient, most recent first. With an organism, "
            "only that organism is returned."
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
        history = _patient_history(app.state.doc, patient_id, organism, app.state.as_of)
        return {"patient_id": patient_id, "organism": organism, "history": history}

    @app.get(
        "/antibiotics",
        tags=["Evidence"],
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
        "/tiers/{organism}",
        tags=["Evidence"],
        summary="Observed resistance list",
        description=(
            "Without `specimen`, returns every specimen's rate list for the "
            "organism. With `specimen`, returns one list and the ward context."
        ),
        response_model=TierListResponse | TierMapResponse,
        responses={
            404: {
                "model": ErrorResponse,
                "description": "Unknown organism or no data for the specimen",
            }
        },
    )
    def get_tiers(
        organism: str = PathParam(description="Organism name."),
        specimen: str | None = Query(
            default=None, description="Specimen; selects the single-list shape."
        ),
        ward_code: str | None = Query(
            default=None, description="When set, adds ward-observed rates."
        ),
    ) -> dict[str, object]:
        doc = app.state.doc
        if specimen is None:
            prefix = f"{organism}|"
            available = {
                key.split("|", 1)[1]: value
                for key, value in doc["antibiotic_tiers"].items()
                if key.startswith(prefix)
            }
            if not available:
                raise HTTPException(
                    status_code=404, detail=f"unknown organism {organism}"
                )
            return {"organism": organism, "tiers": available}
        if app.state.model is not None:
            entries = app.state.model.tiers_for(organism, specimen, ward_code=ward_code)
            if not entries:
                raise HTTPException(
                    status_code=404,
                    detail=f"no data for {organism} in {specimen}",
                )
        else:
            entries = doc["antibiotic_tiers"].get(f"{organism}|{specimen}")
            if entries is None:
                raise HTTPException(
                    status_code=404, detail=f"no tier list for {organism}|{specimen}"
                )
        return {
            "organism": organism,
            "specimen": specimen,
            "context": _context(doc, ward_code),
            "tiers": entries,
        }

    @app.post(
        "/decision-briefs",
        tags=["Decisions"],
        summary="Create a directed decision brief",
        description=(
            "Ranked in-vitro susceptibility options for a known organism, with "
            "data-derived warnings, prior-result context, screens and exclusions. "
            "An in-vitro list, not a prescription."
        ),
        response_model=DecisionBriefResponse,
        responses={
            404: {
                "model": ErrorResponse,
                "description": "Unknown patient or ward, or no data for the culture",
            },
            503: {
                "model": ErrorResponse,
                "description": "Analytics artifact is not loaded",
            },
        },
    )
    def create_decision_brief(request: DecisionBriefRequest) -> dict[str, Any]:
        doc = app.state.doc
        model = app.state.model
        patient = doc.get("patients", {}).get(request.patient_id)
        if patient is None:
            raise HTTPException(
                status_code=404, detail=f"unknown patient {request.patient_id}"
            )
        ward_code = request.encounter.ward_code
        if ward_code not in doc.get("wards", {}):
            raise HTTPException(status_code=404, detail=f"unknown ward {ward_code}")
        if model is None:
            raise HTTPException(
                status_code=503, detail="analytics artifact is not loaded"
            )

        organism = request.culture.organism
        specimen = request.culture.specimen
        entries = model.tiers_for(
            organism, specimen, ward_code=ward_code, include_screens=True
        )
        if not entries:
            raise HTTPException(
                status_code=404,
                detail=f"no susceptibility data for {organism} in {specimen}",
            )

        history = _patient_history(
            doc,
            request.patient_id,
            organism,
            app.state.as_of,
            before=_parse_date(request.culture.culture_date),
        )
        prior_results: dict[str, list[str]] = {}
        for isolate in reversed(history):
            for antibiotic_name, result in isolate["susceptibility"].items():
                prior_results.setdefault(antibiotic_name, []).append(result)

        seen_codes = {entry["antibiotic_code"] for entry in entries}
        options: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []
        for entry in entries:
            meta: AntibioticMetadata = app.state.antibiotic_metadata[
                entry["antibiotic_code"]
            ]
            if meta.role == "screen":
                continue
            prior_result = _latest_prior(prior_results.get(entry["antibiotic"], []))
            enriched = dict(entry)
            enriched["prior_result"] = prior_result
            enriched["prior_resistant"] = prior_result == "R"
            enriched["prior_susceptible"] = prior_result == "S"
            enriched["warnings"] = warnings_for(
                meta, prior_resistant=prior_result == "R"
            )
            options.append(enriched)

        for row in doc.get("antibiotics", []):
            code = row["antibiotic_code"]
            if code in seen_codes:
                continue
            meta = app.state.antibiotic_metadata[code]
            if meta.role == "screen":
                continue
            if meta.reported_for not in ("all", specimen):
                reason = EXCLUSION_NOT_REPORTED_FOR_SPECIMEN
                detail = f"{meta.antibiotic} is not reported for {specimen} specimens."
            else:
                reason = EXCLUSION_NO_SPECIMEN_DATA
                detail = f"No {specimen} susceptibility results for {organism}."
            excluded.append(
                {
                    "antibiotic": meta.antibiotic,
                    "antibiotic_code": code,
                    "reason": reason,
                    "detail": detail,
                }
            )
        excluded.sort(key=lambda entry: (entry["reason"], entry["antibiotic"]))

        options.sort(
            key=lambda entry: (
                entry["observed_resistance"]
                if entry["observed_resistance"] is not None
                else 1.0,
                entry["antibiotic"],
            )
        )
        rank_options(options)

        screens: list[dict[str, Any]] = []
        isolate_pair = _find_isolate(
            doc,
            request.patient_id,
            ward_code=ward_code,
            specimen=specimen,
            organism=organism,
            culture_id=request.culture.culture_id,
            culture_date=request.culture.culture_date,
        )
        if isolate_pair is not None:
            _, isolate = isolate_pair
            for antibiotic_name, result in isolate.get("susceptibility", {}).items():
                code = next(
                    (
                        row["antibiotic_code"]
                        for row in doc.get("antibiotics", [])
                        if row["antibiotic"] == antibiotic_name
                    ),
                    None,
                )
                if code is None:
                    continue
                meta = app.state.antibiotic_metadata[code]
                if meta.role != "screen":
                    continue
                screens.append(
                    {
                        "antibiotic": antibiotic_name,
                        "antibiotic_code": code,
                        "result": result,
                        "interpretation": "screen positive"
                        if result == "R"
                        else "screen negative",
                    }
                )

        if options:
            top = options[0]
            headline = (
                f"Lowest observed resistance among eligible options: "
                f"{top['antibiotic']} ({top['observed_resistance']:.1%}; "
                f"ward n={top['observed_n']})."
            )
        else:
            headline = "No eligible option with specimen-specific data."

        return {
            "request_id": str(uuid4()),
            "generated_at": datetime.now(UTC).isoformat(),
            "data_as_of": str(app.state.as_of) if app.state.as_of else None,
            "headline": headline,
            "context": _context(doc, ward_code),
            "period": {
                "start": doc.get("metadata", {}).get("date_range", {}).get("start"),
                "end": doc.get("metadata", {}).get("date_range", {}).get("end"),
            },
            "options": options,
            "screens": screens,
            "excluded": excluded,
            "patient_history": history[:5],
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
