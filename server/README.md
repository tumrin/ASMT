# resistance-analysis

Data-only analysis of bacterial resistance over the synthetic microbiology dataset,
producing a queryable JSON document and a FastAPI service.

Every field is either read from the dataset CSVs or derived arithmetically from them.
No clinical routes, spectrum, indications, review dates, thresholds or other curated
metadata are used.

## Technology stack

- Python
  - FastAPI, uvicorn for the API
  - Polars, SciPy for data analysis
- Tooling
  - Ruff for linting
  - Ty for type checking
  - uv for project management

## Pipeline stages

| Stage | Module | What happens |
|---|---|---|
| 1 read | `load.py` | Read + schema-validate the CSVs (fails loudly on column drift). |
| 2 analyse | `correlate.py`, `deviations/` | Group rates, rule-based data checks and statistical outliers. |
| 3 log | `report.py` | Write the deviation and outlier logs. No data is changed. |
| 4 structure | `structure.py` | Build the data into a single `dataset.json`. |
| 5 report | `report.py` | Rate tables and a markdown summary. |

### Data-derived fields

- `age_band`: quantile bands computed from the observed `cultures.age_years`; the
  derived edges are stored in `metadata.age_band_edges`.
- `days_since_admission`: `sample_date - admission_date` in days, null for outpatients.
- `n_resistant_classes` / `n_resistant_tests`: distinct resistant classes and the
  number of results per isolate. No MDR cutoff is applied.
- `role`: an antibiotic is a screen if its `class` or name in `antibiotics.csv`
  contains `screen` / `seulonta`.
- flag denominators: a flag applies to isolates that have a result for its marker
  antibiotic in `susceptibility.csv` (MRSA -> cefoxitin screen, VRE -> vancomycin,
  ESBL -> cefuroxime, CPE -> meropenem), restricted to organisms where that flag
  is observed positive in the dataset.

### Deviations

The `consistency` family is rule-based and uses only the data. `consistency.py`
covers cross-table and marker rules:

- `flag_without_marker` — a positive flag with no marker susceptibility result.
- `flag_susceptibility_contradiction` — a positive flag with a susceptible marker.
- `marker_without_flag` — a definitional marker (`mrsa`/`vre`) is resistant but the
  flag is 0. ESBL/CPE are excluded: cefuroxime and meropenem resistance have other
  mechanisms, so a resistant marker there does not imply the flag.
- `agent_specimen_mismatch` — an agent with `reported_for` other than `all` on the
  wrong specimen (the former urine-only rule, generalised).
- `negative_culture_with_isolates` / `positive_culture_without_isolates` / `n_isolates_count_mismatch`.
- `orphan_culture` / `orphan_isolate` / `orphan_susceptibility`.

`plausibility.py` adds field-level checks:
`duplicate_susceptibility_key`, `week_year_mismatch`, `age_birth_year_mismatch`,
`admission_after_sample`, `admission_date_presence`,
`culture_ward_metadata_mismatch`, `specimen_label_mismatch`,
`quantity_format_invalid`, `unknown_result_value`, `duplicate_isolate_no`,
`susceptibility_organism_mismatch`, `unknown_guideline`.

Every consistency finding is reported only — the analysis never removes or rewrites a
record. The JSON document and the evidence endpoints are built from exactly the data
read from the CSVs.

### Outliers

`deviations/outliers.py` reports funnel-plot outliers over the surveillance view. A
cell's rate is compared with a reference rate through the binomial 95% control limits
`p0 ± 1.96·sqrt(p0(1−p0)/n)`:

- `ward_rate_outlier` — `organism × antibiotic × specimen × ward_code` against the same
  `ward_type` pool.
- `weekly_rate_outlier` — `organism × antibiotic × specimen × week` against the whole
  strand, only for weekly cells with at least 30 isolates (the reporting floor in the
  dataset README).

There is no multiple-comparison control, so about 5% of cells fall outside by chance;
the consumer filters by `n` and the cell fields on the endpoint.

## Evidence model

`resistance_core.TierModel` reports observed resistance only:

- `observed_resistance`, `observed_n`, Wilson interval for `organism x antibiotic x
  specimen`, or `organism x antibiotic x specimen x ward_code` when a ward is given;
- `overall_resistance`, `overall_n`, interval for the same organism and specimen
  across all wards;
- `observed_source` is `ward` when the ward cell has data, otherwise `overall`.

No smoothing, prior, tier cutoff, minimum count or reliability label is applied. The
consumer sees `n` and the interval and decides what is strong enough.

## JSON

`output/dataset.json`:

- `metadata` — counts, date range, `as_of`, `age_band_edges`, settings, deviation
  summary and outlier summary.
- `antibiotics` — `antibiotic`, `antibiotic_code`, `antibiotic_fi`, `class`,
  `reported_for`, derived `role` and `marker_flags`.
- `wards.<ward_code>` — volumes, case mix, top `organisms`, per-organism
  `flag_rates_by_organism`, specimen-keyed `resistance_by_antibiotic`, and an
  organism-stratified `antibiogram` (`specimen -> organism -> [antibiotic entries]`).
- `patients.<pid>.wards.<ward_code>.cultures[].isolates[]` with `flags`,
  `n_resistant_classes` and `susceptibility`.
- `antibiotic_tiers["<organism>|<specimen>"]` — observed rate lists.

## Directed decision support

The API implements directed, ward-aware evidence. An organism is assumed known and the
output is an in-vitro susceptibility list, not a prescription.

`POST /decision-briefs`

```json
{
  "patient_id": "P...",
  "encounter": {"ward_code": "ICU", "admission_date": "<admission_date>"},
  "culture": {"organism": "Escherichia coli", "specimen": "urine", "culture_date": "<culture_date>"}
}
```

The response contains:

- `options` — eligible therapeutic agents, sorted by observed resistance, with
  `observed_n`, interval, overall rate, `observed_source`, `rank_group` and
  data-derived warnings (`URINE_ONLY`, `PRIOR_RESISTANT`).
- `screens` — marker results such as the cefoxitin MRSA screen, never mixed into options.
- `excluded` — agents with `not_reported_for_specimen` or `no_specimen_data`.
- `patient_history` — prior same-organism isolates and susceptibility.
- `headline`, `context`, `period`, `data_as_of`, `limitations`.

`rank_group` groups options whose intervals overlap, so the EHR does not present a
meaningful difference where there is none.

## HTTP API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness |
| GET | `/metadata` | counts, settings, deviation and outlier summaries |
| GET | `/patients/{patient_id}` | patient summary + ward list |
| GET | `/patients/{patient_id}/wards/{ward_code}` | single patient x single ward |
| GET | `/wards/{ward_code}` | ward summary with `antibiogram` and `flag_rates_by_organism` |
| GET | `/wards/{ward_code}/patients` | patients seen in a ward |
| GET | `/wards/{ward_code}/antibiogram?specimen=&organism=` | ward evidence |
| GET | `/patients/{patient_id}/history?organism=` | prior isolates and susceptibility |
| GET | `/antibiotics` | antibiotic metadata derived from `antibiotics.csv` |
| POST | `/decision-briefs` | directed decision brief |
| GET | `/tiers/{organism}?specimen=&ward_code=` | observed rate list |
| GET | `/deviations?family=&severity=&detector=` | consistency deviation log |
| GET | `/outliers?detector=&severity=&organism=&antibiotic=&specimen=&ward_code=&week=&min_n=` | statistical outlier log |

## Usage

This is a [uv](https://docs.astral.sh/uv/) workspace and lives in `server/`. Run all
commands from the `server/` directory:

```bash
# from server/
uv sync

# Activate virtual env
source .venv/bin/active.<shell>

uv run resistance-analysis --out output

# 2. serve the artifacts
uv run resistance-api

# tests
uv run pytest
```

`uv sync` creates `.venv/` and installs the workspace packages
(`resistance-analysis`, `resistance-api` and the shared `resistance-core`) plus the
dev group, so no manual activation is needed. `uv run` executes inside that
environment.

Useful flags for the analysis run: `--data-dir`, `--out`, `--all-isolates`
(disable the surveillance rule).

The API reads the four artifacts written by the analysis step, so run the analysis
first. It binds `127.0.0.1:8000` by default; add `--host` / `--port` to change that.

The data directory defaults to the nearest ancestor holding `patients.csv`, or that
ancestor's `data/` subdirectory. Override it with `--data-dir` or the
`RESISTANCE_DATA_DIR` environment variable.

## Layout

A `uv` workspace of three packages: analysis writes the artifacts, the API reads them.

```
packages/
  core/       resistance-core        shared, dependency-light domain logic
    src/resistance_core/
      stats.py                 Wilson interval
      demographics.py          quantile age bands
      tiers.py                 observed-resistance TierModel
      antibiotic_properties.py antibiotic metadata + marker mapping from antibiotics.csv
      decision.py              rank groups and data-derived warnings
  analysis/   resistance-analysis    the pipeline; writes dataset.json etc.
    src/resistance_analysis/
      config.py      runtime settings
      load.py        stage 1: read + validate
      build.py       joins, derived columns, surveillance rule
      resistance.py  derived resistance profile counts
      correlate.py   rates, Wilson CI, Cramer's V, chi-square
      deviations/    consistency checks (consistency.py, plausibility.py) and
                     funnel outliers (outliers.py)
      wards.py       per-ward summaries and per-organism flag rates
      structure.py   stage 4: JSON document
      report.py      stage 5: tables + markdown
      pipeline.py    orchestration
      __main__.py    `resistance-analysis` CLI (run)
  api/        resistance-api         serving layer over the artifacts
    src/resistance_api/
      app.py         FastAPI app + routes
      __main__.py    `resistance-api` CLI (serve)
```

The API imports only `resistance_core` and the artifact files — never the analysis
pipeline. `tests/test_boundary.py` enforces this both statically and at import time.

## Limitations

- The dataset has no diagnosis, dose, route, allergy, renal, severity or outcome data.
  The system cannot determine the clinically correct antibiotic.
- Specimen is not a diagnosis.
- Marker mapping is a rule, but the denominator is the marker results present in
  `susceptibility.csv`.
- Age bands and admission offsets are derived from the data distribution and change
  with the dataset.
- Outlier detection has no multiple-comparison control; about 5% of compared cells can
  fall outside the funnel by chance.
- The consistency checks find nothing on the supplied dataset, which is generated to be
  self-consistent.

## Columns read

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
`duplicate_susceptibility_key` deviation (Deviations and outliers).

## Configuration

`Settings` holds the runtime settings `data_dir`, `out_dir` and `surveillance`, plus
the antibiogram parameters `min_isolates` (30), `green_above` (0.80) and `yellow_above`
(0.60); both cutoffs are exclusive lower bounds. `data_dir` defaults to the nearest ancestor holding `patients.csv` or
`data/patients.csv`, and can be overridden with `RESISTANCE_DATA_DIR` or
`--data-dir`.

## Pipeline specification

| Stage | Module | Action |
|---|---|---|
| 1 read | `load.py` | read + schema validation |
| 2 analyse | `correlate.py`, `deviations/` | group rates, consistency checks, plausibility checks, outliers |
| 3 log | `report.py` | write the deviation and outlier logs (no data is changed) |
| 4 structure | `structure.py`, `wards.py`, `resistance_core` | build `dataset.json` and the antibiogram matrices |
| 5 report | `report.py` | correlation tables + `summary.md` |

The deviation checks run on the raw records. The antibiogram, correlations, ward
rates and outliers run on the first-isolate view (spec.md §6.1). Nothing is filtered or
rewritten between stages.

### Derived fields

| Field | Definition |
|---|---|
| `age_band` | quantile band of `cultures.age_years`; edges stored in `metadata.age_band_edges` |
| `days_since_admission` | `sample_date - admission_date` in days; null for outpatients |
| `is_s` / `is_r` | `susceptibility.result == "S"` / `"R"` |
| `n_resistant_classes` | distinct `antibiotics.class` with `is_r` per isolate |
| `n_resistant_tests` | number of resistant results per isolate |
| `role` | `screen` if `class` or antibiotic name contains `screen` / `seulonta`, else `therapeutic` |
| `marker_flags` | from class/name: MRSA screen → `mrsa`, glycopeptides → `vre`, cephalosporins 2nd gen → `esbl`, carbapenems → `cpe` |

### Correlations

Outcomes: `flag:esbl`, `flag:mrsa`, `flag:vre`, `flag:cpe`, `resistance:any`,
`resistance:antibiotic` (one stratum per antibiotic).

Predictors: `sex`, `home_area`, `ward_type`, `institution`, `ward_code`, `specimen`.

Metrics per outcome × predictor: per-group rate with Wilson 95% interval; chi-square
(no continuity correction) with p and dof; Cramér's V; min/max group rate; reference
group = largest group by n. A comparison needs ≥2 groups. Outcomes pool organisms, so
an association can be driven by case mix.

## Deviations and outliers

Two log families, both reported only: `consistency` (rule-based data checks) and
`statistical` (funnel-plot outliers). Neither changes the data.

### Consistency family

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

### Statistical family (outliers)

For a cell with `n` results and `k` resistant, `k/n` is compared with a reference
rate `p0` and the binomial 95% limits `p0 ± 1.96 · sqrt(p0(1−p0)/n)`, clamped to
`[0, 1]`.

| Detector | Cell | Reference `p0` | Floor |
|---|---|---|---|
| `ward_rate_outlier` | `organism × antibiotic × specimen × ward_code` | same strand within the same `ward_type` | none |
| `weekly_rate_outlier` | `organism × antibiotic × specimen × iso_year/iso_week` | same strand across all weeks | `n ≥ 30` |

There is no multiple-comparison control.

## JSON document (`structure.py`)

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

## HTTP API specification

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | `{"status":"ok"}` |
| GET | `/metadata` | document metadata, available scopes and periods |
| GET | `/antibiogram?scope=&unit=&period=&organism=&specimen=` | filtered matrix (spec.md §6) |
| POST | `/recommendations` | empiric recommendation (spec.md §6.4) |
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

## CLI and outputs

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

## Conflicts

The sections from the top of this file down to Limitations describe the current
implementation. The sections from Columns read onward are the specification moved
from `spec.md`. They disagree on the following points.

| Topic | Current implementation | Specification |
|---|---|---|
| Thresholds | Intro: no thresholds are used. Evidence model: no tier cutoff, minimum count or reliability label. | `min_isolates` (30) reporting floor and traffic light cutoffs `green_above` (0.80) / `yellow_above` (0.60) in `Settings`. |
| Rate measured | Resistance: `observed_resistance`, `overall_resistance` (share R). | Susceptibility: `susceptibility_rate = n_s / n` (share S). |
| Small cells | A rate is always reported; the consumer judges `n` and the interval. | `susceptibility_rate` is null and `traffic_light` is `none` when `n < 30`. |
| Fallback | `observed_source`: the ward cell if it has data, otherwise all wards (`overall`). | `last4w` → `annual` → `hospital` scope while `n < 30`; the response states which scope and period each rate came from. |
| Scopes and periods | Ward or overall, with no period dimension in the evidence model. | `hospital`, `ward` (inpatient) and `region` (outpatient `home_area`), each split into `annual:<year>` and `last4w`. |
| Pipeline stage 4 | `structure.py` builds `dataset.json`. | `structure.py`, `wards.py` and `resistance_core` build `dataset.json` and the antibiogram matrices. |
| Marker flags | Mapped by antibiotic: cefoxitin screen → MRSA, vancomycin → VRE, cefuroxime → ESBL, meropenem → CPE. Flag denominators are limited to organisms where the flag is observed positive. | Mapped by class or name: MRSA screen → `mrsa`, glycopeptides → `vre`, 2nd-gen cephalosporins → `esbl`, carbapenems → `cpe`. No organism restriction is stated. |
| JSON `metadata` | `as_of` | `data_as_of`, plus `source` |
| JSON `wards` | Includes `resistance_by_antibiotic` and a per-ward `antibiogram` (`specimen -> organism -> [entries]`). | Has neither; the antibiogram is top-level and keyed `<scope>\|<unit>\|<period>` → `<organism>\|<specimen>`. |
| JSON tiers | `antibiotic_tiers["<organism>\|<specimen>"]` | Absent. |
| Decision endpoint | `POST /decision-briefs` with `patient_id`, `encounter` (`ward_code`, `admission_date`) and `culture` (`organism`, `specimen`, `culture_date`). | `POST /recommendations` with `scope`, `unit`, `organism` and `specimen`; no patient input. |
| Decision response | `options` sorted by observed resistance, with `rank_group` and warnings (`URINE_ONLY`, `PRIOR_RESISTANT`); also `screens`, `patient_history`, `headline`, `context`, `period`. | `options` ranked by susceptibility rate, with `traffic_light` and the source scope and period; `excluded`, `data_as_of`, `limitations`. A patient's own earlier results are history only and do not change the recommendation, which conflicts with `PRIOR_RESISTANT`. |
| Endpoints only in the current implementation | `/patients/{patient_id}/wards/{ward_code}`, `/wards/{ward_code}/patients`, `/wards/{ward_code}/antibiogram`, `/decision-briefs`, `/tiers/{organism}` | — |
| Endpoints only in the specification | — | `/antibiogram`, `/recommendations`, `/patients` |
| Endpoint parameters | `/patients/{patient_id}/history?organism=`; `/outliers` accepts `severity`. | `/patients/{patient_id}/history` has no `organism` filter; `/outliers` has no `severity` parameter. |
| `/metadata` | Counts, settings, deviation and outlier summaries. | Document metadata plus the available scopes and periods. |
| `core` modules | `tiers.py` (TierModel) and `decision.py` (rank groups, warnings) implement the resistance evidence model. | No package implements `susceptibility_rate`, `traffic_light`, `min_isolates` or `/recommendations` yet. |
