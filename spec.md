# Cumulative antibiogram application

Simple web application that calculates the susceptibility rate of antibiotics per
organism and produces a constantly updating antibiogram for the whole hospital, for
a ward, or for a region.

Every value is read from the supplied CSVs or derived arithmetically from them. Data
can be aggregated, filtered and combined, but is never enriched with outside data.
Nothing is ever removed or rewritten: deviations and outliers are reported and
served, never applied to the data.

## 1. Technology stack

Backend: see `server/README.md`.

Frontend: see `frontend/README.md`.

## 2. End user groups

- Doctor
- Nurse

## 3. Functional requirements

1. **Susceptibility rates.** The backend calculates the susceptibility rate (share of
   isolates tested S) of each antibiotic for each organism × specimen type present in
   the data. Each rate includes the number of isolates used.
   - Count the **first isolate per patient per species per specimen type per
     period** (§6.1).
   - Report a rate only when the cell has **at least 30 isolates**; smaller cells are
     returned with their `n` and a null rate.
2. **Antibiogram view.** A matrix of organisms (rows) × antibiotics (columns).
   - Each row is one organism × specimen type pair: *E. coli* (urine) and *E. coli*
     (blood) are separate rows.
   - **Scope:** whole hospital, or a single unit. The smallest unit depends on
     `ward_type` (§6.2): inpatient (`in`) data is broken down by **ward**, outpatient
     (`out`) data by **region**.
   - **Period:** **annual** (calendar year) and **last four weeks** (the 28 days
     ending at the dataset's latest `sample_date`).
   - Shows all organisms by default; an optional organism filter narrows it. All
     filtering is done by the backend.
   - Each cell gets a traffic light based on its susceptibility rate (§6.3).
3. **Empiric recommendations.** For a new patient whose organism and specimen type are
   known, but whose susceptibility results aren't, the application recommends
   antibiotics ranked by the cumulative susceptibility rates and traffic lights of the
   matching antibiogram row, for the patient's scope. The data in the system is
   historical; a patient's own earlier results are shown as history only and don't
   change the recommendation.
4. **Nice to have: patient view.** A list of patients from which the user can select
   one; the individual view shows basic patient information, the patient's history
   and the empiric recommendations for each finding.
5. **PDF export.** The user can export the antibiogram views and the patient view,
   including their tables, as PDF. This is done entirely in the frontend
   (`frontend/README.md`).

## 4. Non-functional requirements

1. The backend calculates the full (organism, specimen type) × antibiotic matrix for
   each scope and period, and applies the scope, period, organism and specimen
   filters. The frontend only renders the result and does no rate calculations.

## 5. Inputs

### 5.1 Files and keys

| File | Grain | Key |
|---|---|---|
| `patients.csv` | patient | `patient_id` |
| `cultures.csv` | specimen culture | `culture_id` |
| `isolates.csv` | isolate | `isolate_id` |
| `susceptibility.csv` | isolate × antibiotic | (`isolate_id`, `antibiotic_code`) |
| `antibiotics.csv` | antibiotic code table | `antibiotic_code` |
| `wards.csv` | ward code table | `ward_code` |

Join path: `patients (patient_id) → cultures (culture_id) → isolates (isolate_id) →
susceptibility (isolate_id)`.

Columns read and load validation are specified in `server/README.md`.

### 5.2 Organism names

On load, `organism` in `isolates.csv` and `susceptibility.csv` is normalized: trim
surrounding whitespace, lowercase, then replace each run of `.` and whitespace with
`_` (`Escherichia coli` → `escherichia_coli`). Every output and API value, including
the `organism` filter, uses the normalized name. The frontend maps it to a display
name.

## 6. Antibiogram model

### 6.1 Periods and first-isolate rule

| Period | Window |
|---|---|
| `annual` | one calendar year of `sample_date` |
| `last4w` | the 28 days ending at `data_as_of` (max `sample_date`) |

Within each period, only the first isolate per `patient_id × organism × specimen` is
counted, ordered by `sample_date, isolate_id`. The rule is applied per period, so a
patient can contribute one isolate to each year and one to the last-four-weeks window.

### 6.2 Scope

| Scope | Includes |
|---|---|
| `hospital` | all cultures |
| `ward` | cultures with that `ward_code`, for wards with `ward_type = in` |
| `region` | cultures from `ward_type = out` units, grouped by the patient's `home_area` |

### 6.3 Cell

For each scope × period × organism × specimen × antibiotic:

- `n` — first isolates tested against the antibiotic;
- `n_s` — of those, results `S`;
- `susceptibility_rate = n_s / n`, with a Wilson 95% interval; null if `n < 30`;
- `traffic_light`:

| Light | Rule |
|---|---|
| `green` | rate > 80 % |
| `yellow` | 60 % < rate ≤ 80 % |
| `red` | rate ≤ 60 % |
| `none` | `n < 30` (no rate reported) |

The minimum count (30) and the traffic light cutoffs are configurable (see
`server/README.md`).

Applicability: `reported_for="all"` always, `reported_for="urine"` only for urine
specimens; an antibiotic is listed only if it has specimen-specific data for the
organism. Screens are excluded unless `include_screens=True`.

### 6.4 Empiric recommendation

Given a scope (ward or region), organism and specimen, the recommendation is the
matching antibiogram row for the `last4w` period, falling back to `annual` and then to
`hospital` scope when the cell has `n < 30`. Agents are ranked by susceptibility rate;
the response states which scope and period each rate came from.

## 7. Assumptions

- **A1** The data is synthetic (seed 2026) and historical; recommendations are for a
  new patient and use cumulative rates only.
- **A2** Susceptibility is S/R only; no I, MIC or zone diameter.
- **A3** A missing susceptibility row means "not tested", not "susceptible".
- **A4** The only thresholds are the 30-isolate reporting floor and the traffic light
  cutoffs (§6.3), both configurable.
- **A5** "Region" for outpatient units is the patient's `home_area`.
- **A6** "Last four weeks" is relative to the latest `sample_date` in the data, not
  today's date.
- **A7** Organism names are matched exactly after the string normalization in §5.2;
  there is no taxonomy normalisation (e.g. `E. coli` and `Escherichia coli` stay
  distinct).
- **A8** Findings are reported only; the data is never rewritten.

## 8. Limitations and non-goals

- The dataset has no diagnosis, dose, route, allergy, renal, severity or outcome data,
  so the system cannot determine the clinically correct antibiotic; recommendations
  are decision support only.
- Specimen is not a diagnosis.
- The last-four-weeks window will often have cells below 30 isolates.
- VRE and CPE positives are too few for stable rates.
- No authentication or pagination.
