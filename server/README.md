# resistance-analysis

Data-only analysis of bacterial resistance over the synthetic microbiology dataset,
producing a queryable JSON document and a FastAPI service.

Every field is either read from the dataset CSVs or derived arithmetically from them.
No clinical routes, spectrum, indications, review dates, thresholds or other curated
metadata are used.

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
