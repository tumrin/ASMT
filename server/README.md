# resistance-analysis

Cumulative-antibiogram analysis over the synthetic microbiology dataset. The
pipeline reads the six CSVs, computes the susceptibility matrix and the patient
documents, and writes a single JSON artifact; a FastAPI service serves that
artifact.

Every field is either read from the dataset CSVs or derived arithmetically from
them. Data is aggregated, filtered and joined, but never enriched with outside
data. Nothing is removed or rewritten: every record read from the CSVs is served.
The only thresholds are the configurable reporting floor and traffic-light
cutoffs.

## Technology stack

- Python
  - FastAPI, uvicorn for the API
  - Polars for data analysis
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

## Pipeline

| Stage | Module | What happens |
|---|---|---|
| 1 read | `load.py` | Read + schema-validate the CSVs (fails loudly on column drift). |
| 2 build | `build.py` | Culture context, isolate context and the isolate × antibiotic outcome frame. |
| 3 antibiogram | `antibiogram.py` | Periods, first-isolate rule, scopes and susceptibility cells. |
| 4 document | `structure.py` | Assemble `dataset.json`. |
| 5 write | `pipeline.py` | Write the single artifact. |

`build.py` derives `days_since_admission` (`sample_date − admission_date`, null for
outpatients) and the `is_s` / `is_r` outcome flags. No other fields are derived.

## JSON

`output/dataset.json`:

```
{
  "metadata": { source, counts, date_range, data_as_of, settings, scopes, periods },
  "antibiotics": [ { antibiotic, antibiotic_code, antibiotic_fi, class,
                     reported_for, role } ],
  "wards": { "<ward_code>": { ward_code, ward_fi, ward_en, ward_type, institution } },
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
                  "susceptibility": { "<antibiotic>": "R" | "S" } } ] } ] } } },
  "antibiogram": {
    "<scope>|<unit>|<period>": {
      "<organism>|<specimen>": [ { antibiotic, antibiotic_code, class,
          reported_for, role, n, n_s, susceptibility_rate, ci_low, ci_high,
          traffic_light } ] } }
}
```

`<scope>|<unit>` is `hospital|-`, `ward|<ward_code>` or `region|<home_area>`;
`<period>` is `annual:<year>` or `last4w`. `role` is `screen` or `therapeutic`,
derived from the antibiotic's class or name in `antibiotics.csv`. `flags` are the
raw `esbl` / `mrsa` / `vre` / `cpe` columns from `isolates.csv`.

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
| GET | `/wards/{ward_code}` | ward metadata and counts |
| GET | `/wards/{ward_code}/patients` | patients seen in a ward |
| GET | `/antibiotics` | antibiotic metadata derived from `antibiotics.csv` |

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

# 2. serve the artifact
uv run resistance-api

# tests
uv run pytest
```

`uv sync` creates `.venv/` and installs the workspace packages
(`resistance-analysis`, `resistance-api` and the shared `resistance-core`) plus the
dev group, so no manual activation is needed. `uv run` executes inside that
environment.

The analysis takes `--data-dir` and `--out`; it writes `output/dataset.json`. The
API reads that file, so run the analysis first. It binds `127.0.0.1:8000` by
default; add `--host` / `--port` to change that, and `--dataset` to point at
another artifact.

The data directory defaults to the nearest ancestor holding `patients.csv`, or that
ancestor's `data/` subdirectory. Override it with `--data-dir` or the
`RESISTANCE_DATA_DIR` environment variable.

## Layout

A `uv` workspace of three packages: analysis writes the artifact, the API reads it.

```
packages/
  core/       resistance-core        shared, dependency-light domain logic
    src/resistance_core/
      stats.py                 Wilson interval
      antibiotic_properties.py antibiotic metadata (class, reported_for, role) from antibiotics.csv
  analysis/   resistance-analysis    the pipeline; writes dataset.json
    src/resistance_analysis/
      config.py      runtime settings
      load.py        stage 1: read + validate
      build.py       stage 2: joins, derived columns, S/R outcome
      antibiogram.py periods, first-isolate rule, scopes and susceptibility cells
      structure.py   stage 4: JSON document
      pipeline.py    orchestration + write
      __main__.py    `resistance-analysis` CLI (run)
  api/        resistance-api         serving layer over the artifact
    src/resistance_api/
      app.py         FastAPI app + routes
      responses.py   Pydantic response models
      __main__.py    `resistance-api` CLI (serve)
```

The API imports neither `resistance_analysis` nor `resistance_core`; it only serves
the artifact document. `tests/test_boundary.py` enforces this both statically and
at import time.

## Limitations

- The dataset has no diagnosis, dose, route, allergy, renal, severity or outcome data.
  The system cannot determine the clinically correct antibiotic; recommendations are
  decision support only.
- Specimen is not a diagnosis.
- The last-four-weeks window often has cells below 30 isolates, so it falls back to
  the annual period and then to hospital scope.
- VRE and CPE positives are too few for stable rates.
- Organism names are matched exactly; there is no taxonomy normalisation.

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
primary keys (`patient_id`, `culture_id`, `isolate_id`) are validated unique in
`load.py` and a duplicate is a hard load error.

## Configuration

`Settings` holds the runtime settings `data_dir` and `out_dir`, plus the
antibiogram parameters `min_isolates` (30), `green_above` (0.80) and `yellow_above`
(0.60); both cutoffs are exclusive lower bounds. `data_dir` defaults to the nearest
ancestor holding `patients.csv` or `data/patients.csv`, and can be overridden with
`RESISTANCE_DATA_DIR` or `--data-dir`.
