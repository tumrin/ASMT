# User Stories — Cumulative Antibiogram Application

Derived from `server_spec.md`. User groups: **Doctor** and **Nurse**. Technical stories (backend/data) are written from the perspective of the development team where no end user is the direct actor.

Acceptance criteria use the shared definitions at the end of this document (see [Definitions](#definitions)).

---

## Epic 1 — Hospital & ward antibiogram

### US-1.1 Hospital-wide antibiogram
**As a** doctor,
**I want to** see an antibiogram for the whole hospital,
**so that** I can choose effective empirical antibiotic therapy based on local resistance data.

**Acceptance criteria**
- A hospital-level antibiogram view is available from the main navigation.
- The view shows a matrix of organisms × antibiotics with resistance percentages.
- Each cell shows the number of isolates used in the calculation.
- Cells with fewer than 30 isolates show no percentage (e.g. "–" / "insufficient data") but may show the isolate count.
- Data comes only from the provided CSV files.

### US-1.2 Ward-specific antibiogram
**As a** doctor,
**I want to** filter the antibiogram to my own ward,
**so that** I get up-to-date information on the susceptibility profile of bacteria in my ward.

**Acceptance criteria**
- The user can select "All wards" or a single ward (from `wards.csv`, shown by name).
- Changing the ward updates the table without a full page reload.
- The 30-isolate threshold and first-isolate rule apply to the ward-level data as well.

### US-1.3 Annual and monthly periods
**As a** doctor,
**I want to** switch between annual and monthly views,
**so that** I can see both the long-term resistance level and recent trends.

**Acceptance criteria**
- The user can choose the timescale: annual or monthly.
- The user can choose the specific year (and month, in monthly mode).
- The first-isolate deduplication is performed per selected period (a patient's isolate may count once per month in monthly view, and once per year in annual view).

### US-1.4 Filter by organism
**As a** doctor or nurse,
**I want to** filter the antibiogram to a specific organism,
**so that** I can quickly see which antibiotics work against the bacterium I'm dealing with.

**Acceptance criteria**
- An organism filter lists every organism present in the data.
- Selecting an organism shows only that organism's row(s)/antibiotic results.
- Filters (ward, period, organism, specimen type) can be combined.

### US-1.5 Filter by specimen type
**As a** doctor,
**I want to** filter results by specimen type (blood, urine, wound),
**so that** I see resistance data relevant to the infection site.

**Acceptance criteria**
- Specimen type is a selectable filter.
- Antibiotics with `reported_for = urine` (e.g. mecillinam) are shown only for urine specimens.

### US-1.6 Traffic-light colouring
**As a** nurse or doctor,
**I want** each antibiotic result coloured green, yellow or red,
**so that** I can see good, okay and bad treatment options at a glance.

**Acceptance criteria**
- Green = antibiotic works well (low resistance), yellow = medium, red = works badly (high resistance).
- Thresholds are defined in one place and documented (see Definitions).
- Cells without a reportable percentage (< 30 isolates) are neutral/grey, not coloured.
- A legend explaining the colours is visible in the view.
- Colour is not the only indicator (percentage is always shown) for accessibility.

---

## Epic 2 — Resistance calculation (backend)

### US-2.1 Compute resistance rates per organism and antibiotic
**As a** development team,
**we want** the backend to compute resistance percentages for every organism and antibiotic in the data,
**so that** the frontend only renders results and all clinical logic lives in one place.

**Acceptance criteria**
- Calculations are done in Python with Polars (SciPy where statistics are needed).
- Resistance % = R / (S + R) × 100 among the counted isolates.
- Results are computed for every organism present in the data.
- Each result includes: organism, antibiotic, ward (or hospital), specimen type, period, number of isolates, number resistant, resistance % (or null).

### US-2.2 First isolate per patient rule
**As a** doctor,
**I want** only the first isolate per patient per species per specimen type per period to be counted,
**so that** patients with repeated samples don't skew the resistance rates.

**Acceptance criteria**
- Isolates are joined to cultures to get patient, sample date, specimen and ward.
- For each (patient, organism, specimen type, period) only the isolate from the earliest sample date is counted.
- For the ward and region scopes the rule is applied per setting (adding `ward_type`), so an inpatient isolate and an outpatient isolate from the same patient do not suppress each other; the hospital scope spans settings and keeps the single global first isolate.
- Ties on the same date are resolved deterministically (e.g. lowest `culture_id` / `isolate_no`).
- Unit tests cover deduplication with repeated samples from the same patient.

### US-2.3 Minimum 30 isolates
**As a** doctor,
**I want** percentages reported only when at least 30 isolates were tested,
**so that** I don't make decisions based on statistically unreliable numbers.

**Acceptance criteria**
- If the counted isolate number is < 30, the API returns the isolate count but `resistance_pct = null`.
- The frontend displays such cells as "insufficient data".

### US-2.4 Antibiogram API
**As a** frontend developer,
**I want** a FastAPI endpoint that returns antibiogram data for given filters,
**so that** the UI can build the filterable table.

**Acceptance criteria**
- Endpoint accepts filters: ward (optional), period type (year/month), period value, organism (optional), specimen type (optional).
- Endpoints for filter options: list of wards, organisms, specimen types, available periods.
- Responses are typed (Pydantic models) and documented in the auto-generated OpenAPI docs.

### US-2.5 Constantly updating antibiogram
**As a** doctor,
**I want** the antibiogram to reflect the latest data,
**so that** I always see current information.

**Acceptance criteria**
- When the CSV files are updated, the results are recomputed (on startup and/or on file change / reload endpoint) without code changes.
- The view shows the date of the latest sample included in the data.

### US-2.6 No data enrichment
**As a** development team,
**we want** to use only the six provided CSV files,
**so that** the application complies with the data-use rules.

**Acceptance criteria**
- Only `antibiotics.csv`, `cultures.csv`, `isolates.csv`, `patients.csv`, `susceptibility.csv` and `wards.csv` are read.
- Data is only aggregated, filtered and joined; no external datasets, breakpoints or reference data are added.

---

## Epic 3 — Patient view

### US-3.1 List inpatients
**As a** nurse,
**I want to** see a list of all inpatients,
**so that** I can find the patient I am caring for.

**Acceptance criteria**
- The list includes patients with cultures from wards where `ward_type = in`.
- Each row shows basic info (patient ID, sex, age/birth year, ward).
- The list can be searched/filtered (e.g. by patient ID or ward).
- The patient view is a separate page from the antibiogram view.

### US-3.2 Patient details
**As a** doctor,
**I want to** open an individual patient and see their basic information and culture findings,
**so that** I understand what infection the patient has.

**Acceptance criteria**
- Shows patient info from `patients.csv` (sex, birth year, home area) and current ward/admission date from `cultures.csv`.
- Lists the patient's cultures: sample date, specimen type, result, organism(s) found and resistance markers (ESBL, MRSA, VRE, CPE).
- Shows the patient's own susceptibility results (S/R per antibiotic) when available.

### US-3.3 Antibiotic recommendations for a patient
**As a** doctor,
**I want** the patient view to recommend antibiotics based on the patient's organism and the local susceptibility rates,
**so that** I can choose an effective treatment quickly.

**Acceptance criteria**
- For each organism found in the patient, the view shows a focused antibiogram: the antibiotics for that organism, specimen type and the patient's ward (falling back to hospital-level when the ward has < 30 isolates — the level used is shown).
- Antibiotics are sorted by resistance % (lowest first) and coloured with the traffic-light system.
- Antibiotics to which the patient's own isolate tested resistant (R) are marked as not recommended, regardless of the cumulative rate.
- Antibiotics not relevant for the specimen type (`reported_for`) are hidden.
- The recommendation is labelled as decision support, not a prescription.

---

## Epic 4 — PDF reports

### US-4.1 Antibiogram PDF
**As a** doctor,
**I want to** export the current hospital or ward antibiogram as a PDF,
**so that** I can print it, share it or put it on the ward notice board.

**Acceptance criteria**
- An "Export PDF" button is available in the antibiogram view.
- The PDF contains the table as filtered, including traffic-light colours, isolate counts and the legend.
- The PDF header shows the hospital/ward, period, filters used and generation date.

### US-4.2 Patient PDF
**As a** doctor or nurse,
**I want to** export the patient view as a PDF,
**so that** I can attach it to records or discuss it with colleagues.

**Acceptance criteria**
- An "Export PDF" button is available in the patient view.
- The PDF includes patient basic info, findings and the recommended antibiotics table.
- The PDF shows the generation date and data source period.

---

## Epic 5 — Development tooling

### US-5.1 Project setup and quality
**As a** development team,
**we want** a consistent project setup,
**so that** the code is easy to run and maintain.

**Acceptance criteria**
- Backend is managed with `uv`, linted with `ruff` and type-checked with `ty` with no errors.
- Backend runs with FastAPI + uvicorn.
- Frontend uses React + Vite + TypeScript.
- A README explains how to start backend and frontend.

---

## Definitions

| Term | Definition |
|---|---|
| **Counted isolate** | First isolate per patient per species per specimen type per period (earliest sample date); per setting (`ward_type`) for the ward and region scopes. |
| **Resistance %** | Resistant (R) counted isolates ÷ tested counted isolates × 100. Data contains only S and R results. |
| **Susceptibility %** | 100 − resistance %. Shown in the matrix where "how effective the antibiotic is" is needed. |
| **Reportable** | At least 30 counted isolates for the organism/antibiotic/filter combination. |
| **Traffic light** (proposed, to be confirmed with clinicians) | Green: resistance < 10 %; Yellow: 10–20 %; Red: > 20 %; Grey: not reportable. |
| **Period** | Calendar year (annual) or calendar month (monthly), based on `sample_date`. |
| **Inpatient** | Patient with a culture from a ward where `ward_type = in`. |

## Open questions

1. What exact traffic-light thresholds should be used? (Proposal above.)
2. Should the "current" inpatient list be based on the latest culture only, or any culture within a recent time window?
3. Do nurses and doctors need different permissions or views, or is the UI the same for both?
4. Should the ward antibiogram fall back to hospital level automatically when isolate counts are too low, or just show "insufficient data"?
