# resistance-analysis

Data-only analysis of bacterial susceptibility over the synthetic microbiology
dataset, producing a queryable JSON document and a FastAPI service.

Every field is either read from the dataset CSVs or derived arithmetically from
them. Data is aggregated, filtered and joined, but never enriched with outside
data. Nothing is removed or rewritten: deviations and outliers are reported and
served, never applied to the data. The only thresholds are the configurable
reporting floor and traffic-light cutoffs.

## Technology stack

- Python
  - FastAPI, uvicorn for the API
  - Polars, SciPy for data analysis
- Tooling
  - Ruff for linting
  - Ty for type checking
  - uv for project management

## Antibiogram model

### Periods and first-isolate rule

| Period | Window |
|---|---|
| `annual:<year>` | one calendar year of `sample_date` |
| `last4w` | the 28 days ending at `data_as_of` (max `sample_date`) |

Within each period, only the first isolate per `patient_id × organism × specimen`
is counted, ordered by `sample_date, isolate_id`. The rule is applied per period,
so a patient can contribute one isolate to each year and one to the
last-four-weeks window.

### Scope

| Scope | Includes |
|---|---|
| `hospital` | all cultures (`unit` is `-`) |
| `ward` | cultures with that `ward_code`, for wards with `ward_type = in` |
| `region` | cultures from `ward_type = out` units, grouped by the patient's `home_area` |

### Cell

For each scope × period × organism × specimen × antibiotic:

- `n` — first isolates tested against the antibiotic;
- `n_s` — of those, results `S`;
- `susceptibility_rate = n_s / n` with a Wilson 95% interval; `null` if `n` is
  below `min_isolates`;
- `traffic_light`: `green` above `green_above`, `yellow` above `yellow_above`,
  otherwise `red`; `none` when the rate is not reported.

Applicability: `reported_for="all"` always, `reported_for="urine"` only for urine
specimens; an antibiotic is listed only if it has specimen-specific data for the
organism. Screens are stored with `role="screen"` and filtered by the API unless
`include_screens=true`.

The minimum count (30) and the traffic-light cutoffs (`0.80` / `0.60`) are
configurable in `Settings` and reported in `metadata.settings`.

### Empiric recommendation

Given a scope, unit, organism and specimen, the recommendation ranks therapeutic
agents by cumulative susceptibility. The starting period is `last4w` (or the
requested `annual:<year>`); when a cell has fewer than `min_isolates` isolates it
falls back from the starting period to `annual` and then to `hospital` scope. Each
option reports the scope and period its rate came from. A patient's own earlier
results are history only and do not change a recommendation.

## Pipeline stages

| Stage | Module | What happens |
|---|---|---|
| 1 read | `load.py` | Read + schema-validate the CSVs (fails loudly on column drift). |
| 2 analyse | `correlate.py`, `deviations/` | Group rates, rule-based data checks and statistical outliers. |
| 3 log | `report.py` | Write the deviation and outlier logs. No data is changed. |
| 4 structure | `structure.py`, `antibiogram.py`, `wards.py`, `resistance_core` | Build `dataset.json` and the antibiogram matrix. |
| 5 report | `report.py` | Rate tables and a markdown summary. |

The deviation checks run on the raw records. Correlations, ward rates, outliers
and the antibiogram run on the first-isolate view (per period for the
antibiogram). Nothing is filtered or rewritten between stages.

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

## Deviations

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

## Outliers

`deviations/outliers.py` reports funnel-plot outliers over the surveillance view. A
cell's rate is compared with a reference rate through the binomial 95% control limits
`p0 ± 1.96·sqrt(p0(1−p0)/n)`:

- `ward_rate_outlier` — `organism × antibiotic × specimen × ward_code` against the same
  `ward_type` pool.
- `weekly_rate_outlier` — `organism × antibiotic × specimen × week` against the whole
  strand, only for weekly cells with at least 30 isolates.

There is no multiple-comparison control, so about 5% of cells fall outside by chance;
the consumer filters by `n` and the cell fields on the endpoint.

## JSON

`output/dataset.json`:

```
{
  "metadata": { source, counts, date_range, data_as_of, age_band_edges, settings,
                scopes, periods, deviation_summary, outlier_summary },
  "antibiotics": [ { antibiotic, antibiotic_code, antibiotic_fi, class,
                     reported_for, role, marker_flags } ],
  "wards": { "<ward_code>": { ward_fi, ward_en, ward_type, institution, date_range,
             counts, cultures_by_specimen, cultures_by_result, organisms,
             flag_rates_by_organism, basis } },
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

## HTTP API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness |
| GET | `/metadata` | counts, settings, available scopes and periods |
| GET | `/antibiogram?scope=&unit=&period=&organism=&specimen=&include_screens=` | filtered susceptibility matrix |
| GET | `/recommendations?scope=&unit=&organism=&specimen=&period=` | empiric antibiotic ranking |
| GET | `/patients` | patient list |
| GET | `/patients/{patient_id}` | patient summary + ward list |
| GET | `/patients/{patient_id}/history?organism=` | prior isolates and susceptibility |
| GET | `/patients/{patient_id}/wards/{ward_code}` | single patient x single ward |
| GET | `/wards/{ward_code}` | ward summary |
| GET | `/wards/{ward_code}/patients` | patients seen in a ward |
| GET | `/antibiotics` | antibiotic metadata derived from `antibiotics.csv` |
| GET | `/deviations?family=&severity=&detector=` | consistency deviation log |
| GET | `/outliers?detector=&organism=&antibiotic=&specimen=&ward_code=&week=&min_n=` | statistical outlier log |

`GET /recommendations` query (same params as `/antibiogram`; `organism` and
`specimen` are required):

```
scope=ward&unit=ICU&organism=Escherichia%20coli&specimen=urine
```

Response: `options` (therapeutic agents ranked by susceptibility rate, with `n`,
interval, `traffic_light` and the `source_scope` / `source_unit` / `source_period`
the rate came from), `excluded` (`not_reported_for_specimen` or
`no_specimen_data`), `data_as_of`, `limitations`.

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
(disable the first-isolate rule).

The API reads the artifacts written by the analysis step, so run the analysis
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
      antibiotic_properties.py antibiotic metadata + marker mapping from antibiotics.csv
  analysis/   resistance-analysis    the pipeline; writes dataset.json etc.
    src/resistance_analysis/
      config.py      runtime settings
      load.py        stage 1: read + validate
      build.py       joins, derived columns
      resistance.py  derived resistance profile counts
      antibiogram.py periods, first-isolate rule, scopes and susceptibility cells
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
      responses.py   Pydantic response models
      __main__.py    `resistance-api` CLI (serve)
```

The API imports only `resistance_core` and the artifact files — never the analysis
pipeline. `tests/test_boundary.py` enforces this both statically and at import time.

## Limitations

- The dataset has no diagnosis, dose, route, allergy, renal, severity or outcome data.
  The system cannot determine the clinically correct antibiotic; recommendations are
  decision support only.
- Specimen is not a diagnosis.
- The last-four-weeks window often has cells below 30 isolates, so it falls back to
  the annual period and then to hospital scope.
- VRE and CPE positives are too few for stable rates.
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
`duplicate_susceptibility_key` deviation (Deviations).

## Configuration

`Settings` holds the runtime settings `data_dir`, `out_dir` and `surveillance`, plus
the antibiogram parameters `min_isolates` (30), `green_above` (0.80) and `yellow_above`
(0.60); both cutoffs are exclusive lower bounds. `data_dir` defaults to the nearest
ancestor holding `patients.csv` or `data/patients.csv`, and can be overridden with
`RESISTANCE_DATA_DIR` or `--data-dir`.

## Correlations

Outcomes: `flag:esbl`, `flag:mrsa`, `flag:vre`, `flag:cpe`, `resistance:any`,
`resistance:antibiotic` (one stratum per antibiotic).

Predictors: `sex`, `home_area`, `ward_type`, `institution`, `ward_code`, `specimen`.

Metrics per outcome × predictor: per-group rate with Wilson 95% interval; chi-square
(no continuity correction) with p and dof; Cramér's V; min/max group rate; reference
group = largest group by n. A comparison needs ≥2 groups. Outcomes pool organisms, so
an association can be driven by case mix.

## Deviation and outlier detectors

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
| `ward_rate_outlier` | `organism × antibiotic × specimen × ward_code` outside the same-`ward_type` funnel | warning |
| `weekly_rate_outlier` | `organism × antibiotic × specimen × week` outside the strand funnel (n ≥ 30) | warning |

ESBL and CPE are mechanism flags, so a resistant marker there does not imply the flag.
For a cell with `n` results and `k` resistant, `k/n` is compared with a reference rate
`p0` and the binomial 95% limits `p0 ± 1.96 · sqrt(p0(1−p0)/n)`, clamped to `[0, 1]`.
There is no multiple-comparison control.

## CLI and outputs

```
uv run resistance-analysis --out output [--data-dir ...]
uv run resistance-api --dataset output/dataset.json
                      --deviations output/deviations.csv
                      --outliers output/outliers.csv
```

Outputs: `dataset.json`, `analytics.csv`, `deviations.csv` / `deviations.jsonl`,
`outliers.csv` / `outliers.jsonl`, `report/correlations_summary.csv`,
`report/group_rates.csv`, `summary.md`.
