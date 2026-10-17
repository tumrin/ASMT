# Cumulative antibiogram application

Simple web application that calculates the susceptibility rate of antibiotics per
organism and produces a constantly updating antibiogram for the whole hospital, for
a ward, or for a region.

Every value is read from the supplied CSVs or derived arithmetically from them. Data
can be aggregated, filtered and combined, but is never enriched with outside data.
Nothing is ever removed or rewritten: deviations and outliers are reported and
served, never applied to the data.

## 1. Technology stack

### Backend

- Python
  - FastAPI, uvicorn for the API
  - Polars, SciPy for data analysis
- Tooling
  - Ruff for linting
  - Ty for type checking
  - uv for project management

### Frontend

React, Vite, TypeScript

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
   including their tables, as PDF. This is done entirely in the frontend.

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

### 5.2 Columns read

- `patients`: `patient_id, sex, birth_year, home_area`
- `cultures`: `culture_id, patient_id, age_years, sample_date, iso_year, iso_week,
  ward_code, ward_fi, ward_en, ward_type, institution, admission_date, specimen,
  specimen_fi, result, n_isolates`
- `isolates`: `isolate_id, culture_id, isolate_no, organism, quantity, esbl, mrsa,
  vre, cpe`
- `susceptibility`: `isolate_id, culture_id, organism, antibiotic, antibiotic_code,
  antibiotic_fi, result, guideline`
- `antibiotics`: `antibiotic, antibiotic_code, antibiotic_fi, class, reported_for`
- `wards`: `ward_code, ward_fi, ward_en, ward_type, institution`

Empty strings are read as null. Dates are ISO strings parsed to dates. The three
primary keys are validated unique in `load.py` and a duplicate is a hard load error.
A duplicate `(isolate_id, antibiotic_code)` is not a load error; it is reported as a
`duplicate_susceptibility_key` deviation (§9).

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

The minimum count (30) and the traffic light cutoffs live in `Settings` (§7).

Applicability: `reported_for="all"` always, `reported_for="urine"` only for urine
specimens; an antibiotic is listed only if it has specimen-specific data for the
organism. Screens are excluded unless `include_screens=True`.

### 6.4 Empiric recommendation

Given a scope (ward or region), organism and specimen, the recommendation is the
matching antibiogram row for the `last4w` period, falling back to `annual` and then to
`hospital` scope when the cell has `n < 30`. Agents are ranked by susceptibility rate;
the response states which scope and period each rate came from.

## 7. Configuration

`Settings` holds the runtime settings `data_dir`, `out_dir` and `surveillance`, plus
the antibiogram parameters `min_isolates` (30), `green_above` (0.80) and `yellow_above`
(0.60); both cutoffs are exclusive lower bounds. `data_dir` defaults to the nearest ancestor holding `patients.csv` or
`data/patients.csv`, and can be overridden with `RESISTANCE_DATA_DIR` or
`--data-dir`.

## 8. Pipeline stages

| Stage | Module | Action |
|---|---|---|
| 1 read | `load.py` | read + schema validation |
| 2 analyse | `correlate.py`, `deviations/` | group rates, consistency checks, plausibility checks, outliers |
| 3 log | `report.py` | write the deviation and outlier logs (no data is changed) |
| 4 structure | `structure.py`, `wards.py`, `resistance_core` | build `dataset.json` and the antibiogram matrices |
| 5 report | `report.py` | correlation tables + `summary.md` |

The deviation checks run on the raw records. The antibiogram, correlations, ward
rates and outliers run on the first-isolate view (§6.1). Nothing is filtered or
rewritten between stages.

### 8.1 Derived fields

| Field | Definition |
|---|---|
| `age_band` | quantile band of `cultures.age_years`; edges stored in `metadata.age_band_edges` |
| `days_since_admission` | `sample_date - admission_date` in days; null for outpatients |
| `is_s` / `is_r` | `susceptibility.result == "S"` / `"R"` |
| `n_resistant_classes` | distinct `antibiotics.class` with `is_r` per isolate |
| `n_resistant_tests` | number of resistant results per isolate |
| `role` | `screen` if `class` or antibiotic name contains `screen` / `seulonta`, else `therapeutic` |
| `marker_flags` | from class/name: MRSA screen → `mrsa`, glycopeptides → `vre`, cephalosporins 2nd gen → `esbl`, carbapenems → `cpe` |

### 8.2 Correlations

Outcomes: `flag:esbl`, `flag:mrsa`, `flag:vre`, `flag:cpe`, `resistance:any`,
`resistance:antibiotic` (one stratum per antibiotic).

Predictors: `sex`, `home_area`, `ward_type`, `institution`, `ward_code`, `specimen`.

Metrics per outcome × predictor: per-group rate with Wilson 95% interval; chi-square
(no continuity correction) with p and dof; Cramér's V; min/max group rate; reference
group = largest group by n. A comparison needs ≥2 groups. Outcomes pool organisms, so
an association can be driven by case mix.

## 9. Deviations and outliers

Two log families, both reported only: `consistency` (rule-based data checks) and
`statistical` (funnel-plot outliers). Neither changes the data.

### 9.1 Consistency family

| Detector | Rule | Severity |
|---|---|---|
| `flag_without_marker` | positive flag with no marker susceptibility result | warning |
| `flag_susceptibility_contradiction` | positive flag but the marker result is S | critical |
| `marker_without_flag` | a definitional marker (`mrsa`, `vre`) result is R but the flag is 0 | critical |
| `agent_specimen_mismatch` | `reported_for` is not "all" and the specimen differs | warning |
| `negative_culture_with_isolates` | `result="negative"` and ≥1 isolate | critical |
| `positive_culture_without_isolates` | `result="positive"` and 0 isolates | warning |
| `n_isolates_count_mismatch` | declared `n_isolates` ≠ actual rows | warning |
| `orphan_culture` / `orphan_isolate` / `orphan_susceptibility` | dangling foreign key | critical |
| `duplicate_susceptibility_key` | `(isolate_id, antibiotic_code)` appears more than once | critical |
| `week_year_mismatch` | `iso_year`/`iso_week` ≠ ISO year/week of `sample_date` | warning |
| `age_birth_year_mismatch` | `age_years` differs by more than 1 from `sample_year − birth_year` | warning |
| `admission_after_sample` | `admission_date > sample_date` | critical |
| `admission_date_presence` | inpatients lack an `admission_date`, or outpatients have one | warning |
| `culture_ward_metadata_mismatch` | culture ward fields differ from `wards.csv` (or unknown `ward_code`) | warning |
| `specimen_label_mismatch` | `specimen_fi` is not the label the dataset uses for that `specimen` | warning |
| `quantity_format_invalid` | `quantity` shape differs from the shape that specimen uses | warning |
| `unknown_result_value` | `result` outside `positive`/`negative`/`mixed_growth` | critical |
| `duplicate_isolate_no` | `isolate_no` repeated within a culture | warning |
| `susceptibility_organism_mismatch` | `susceptibility.organism` ≠ the isolate organism | critical |
| `unknown_guideline` | `guideline` is null or not `EUCAST <year>` | warning |

ESBL and CPE are mechanism flags, so a resistant marker there does not imply the flag.

### 9.2 Statistical family (outliers)

For a cell with `n` results and `k` resistant, `k/n` is compared with a reference
rate `p0` and the binomial 95% limits `p0 ± 1.96 · sqrt(p0(1−p0)/n)`, clamped to
`[0, 1]`.

| Detector | Cell | Reference `p0` | Floor |
|---|---|---|---|
| `ward_rate_outlier` | `organism × antibiotic × specimen × ward_code` | same strand within the same `ward_type` | none |
| `weekly_rate_outlier` | `organism × antibiotic × specimen × iso_year/iso_week` | same strand across all weeks | `n ≥ 30` |

There is no multiple-comparison control.

## 10. JSON document (`structure.py`)

```
{
  "metadata": { source, counts, date_range, data_as_of, age_band_edges, settings,
                deviation_summary, outlier_summary },
  "antibiotics": [ { antibiotic, antibiotic_code, antibiotic_fi, class,
                     reported_for, role, marker_flags } ],
  "wards": { "<ward_code>": { ward_fi, ward_en, ward_type, institution, date_range,
             counts, cultures_by_specimen, cultures_by_result, organisms,
             flag_rates_by_organism } },
  "patients": {
    "<patient_id>": {
      patient_id, sex, birth_year, home_area,
      "wards": {
        "<ward_code>": {
          ward_code, ward_fi, ward_en, ward_type, institution,
          "cultures": [
            { culture_id, sample_date, iso_year, iso_week, age_years, specimen,
              result, n_isolates, days_since_admission,
              "isolates": [
                { isolate_id, isolate_no, organism, quantity,
                  "flags": { esbl, mrsa, vre, cpe },
                  n_resistant_classes,
                  "susceptibility": { "<antibiotic>": "R" | "S" } } ] } ] } } },
  "antibiogram": {
    "<scope>|<unit>|<period>": {
      "<organism>|<specimen>": [ { antibiotic, antibiotic_code, class,
          reported_for, role, n, n_s, susceptibility_rate, ci_low, ci_high,
          traffic_light } ] } }
}
```

`<scope>|<unit>` is `hospital|-`, `ward|<ward_code>` or `region|<home_area>`;
`<period>` is `annual:<year>` or `last4w`.

## 11. HTTP API

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | `{"status":"ok"}` |
| GET | `/metadata` | document metadata, available scopes and periods |
| GET | `/antibiogram?scope=&unit=&period=&organism=&specimen=` | filtered matrix (§6) |
| POST | `/recommendations` | empiric recommendation (§6.4) |
| GET | `/antibiotics` | metadata derived from `antibiotics.csv` |
| GET | `/wards/{ward_code}` | ward summary |
| GET | `/patients` | *nice to have:* patient list |
| GET | `/patients/{patient_id}` | *nice to have:* summary + ward list |
| GET | `/patients/{patient_id}/history` | *nice to have:* prior isolates and susceptibility |
| GET | `/deviations?family=&severity=&detector=` | consistency deviation log |
| GET | `/outliers?detector=&organism=&antibiotic=&specimen=&ward_code=&week=&min_n=` | statistical outlier log |

`POST /recommendations` request:

```json
{
  "scope": "ward",
  "unit": "ICU",
  "organism": "Escherichia coli",
  "specimen": "urine"
}
```

Response: `options` (therapeutic agents ranked by susceptibility rate, with `n`,
interval, `traffic_light`, and the scope and period the rate came from), `excluded`
(`not_reported_for_specimen` or `no_specimen_data`), `data_as_of`, `limitations`.

## 12. CLI and outputs

```
uv run resistance-analysis --out output [--data-dir ...]
uv run resistance-api --dataset output/dataset.json
                      --analytics output/analytics.csv
                      --deviations output/deviations.csv
                      --outliers output/outliers.csv
```

Outputs: `dataset.json`, `analytics.csv`, `deviations.csv` / `deviations.jsonl`,
`outliers.csv` / `outliers.jsonl`, `report/correlations_summary.csv`,
`report/group_rates.csv`, `summary.md`.

## 13. Assumptions

- **A1** The data is synthetic (seed 2026) and historical; recommendations are for a
  new patient and use cumulative rates only.
- **A2** Susceptibility is S/R only; no I, MIC or zone diameter.
- **A3** A missing susceptibility row means "not tested", not "susceptible".
- **A4** The only thresholds are the 30-isolate reporting floor and the traffic light
  cutoffs (§6.3), both configurable.
- **A5** "Region" for outpatient units is the patient's `home_area`.
- **A6** "Last four weeks" is relative to the latest `sample_date` in the data, not
  today's date.
- **A7** Organism names are matched exactly; there is no taxonomy normalisation.
- **A8** Findings are reported only; the data is never rewritten.

## 14. Limitations and non-goals

- The dataset has no diagnosis, dose, route, allergy, renal, severity or outcome data,
  so the system cannot determine the clinically correct antibiotic; recommendations
  are decision support only.
- Specimen is not a diagnosis.
- The last-four-weeks window will often have cells below 30 isolates.
- VRE and CPE positives are too few for stable rates.
- No authentication or pagination.
