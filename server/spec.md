# Specification and assumptions

Current behaviour of `resistance-analysis`. Every value is read from the supplied CSVs
or derived arithmetically from them. No curated clinical metadata, review dates or
invented thresholds are used. Nothing is ever removed or rewritten: deviations and
outliers are reported and served, never applied to the data.

## 1. Purpose

Given the synthetic microbiology dataset (`patients`, `cultures`, `isolates`,
`susceptibility`, `antibiotics`, `wards`), the program:

1. reads and validates the inputs;
2. finds group-rate associations, detects rule-based inconsistencies and flags
   statistical outliers;
3. logs the inconsistencies and outliers (no data is changed);
4. structures the data into a single JSON document;
5. serves directed, ward-aware in-vitro susceptibility evidence over HTTP, and exposes
   the deviation and outlier logs on separate endpoints.

## 2. Inputs

### 2.1 Files and keys

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

### 2.2 Columns read

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
`duplicate_susceptibility_key` deviation (§7).

## 3. Configuration

`Settings` contains only runtime settings: `data_dir`, `out_dir` and `surveillance`.
There are no clinical thresholds and no version fields. `data_dir` defaults to the
nearest ancestor holding `patients.csv` or `data/patients.csv`, and can be overridden
with `RESISTANCE_DATA_DIR` or `--data-dir`.

## 4. Pipeline stages

| Stage | Module | Action |
|---|---|---|
| 1 read | `load.py` | read + schema validation |
| 2 analyse | `correlate.py`, `deviations/` | group rates, consistency checks, plausibility checks, outliers |
| 3 log | `report.py` | write the deviation and outlier logs (no data is changed) |
| 4 structure | `structure.py`, `wards.py`, `resistance_core.TierModel` | build `dataset.json` |
| 5 report | `report.py` | correlation tables + `summary.md` |

The deviation checks run on the raw records (`deviations/consistency.py`,
`deviations/plausibility.py`). The correlations, tier lists, ward rates and outliers run
on the first-isolate surveillance view (§5.1). Nothing is filtered or rewritten between
stages, so the JSON document contains exactly the records read in stage 1.

## 5. Derived fields

| Field | Definition |
|---|---|
| `age_band` | quantile band of `cultures.age_years`; edges stored in `metadata.age_band_edges` |
| `days_since_admission` | `sample_date - admission_date` in days; null for outpatients |
| `is_r` | `susceptibility.result == "R"` |
| `n_resistant_classes` | distinct `antibiotics.class` with `is_r` per isolate |
| `n_resistant_tests` | number of resistant results per isolate |
| `role` | `screen` if `class` or antibiotic name contains `screen` / `seulonta`, else `therapeutic` |
| `marker_flags` | from class/name: MRSA screen → `mrsa`, glycopeptides → `vre`, cephalosporins 2nd gen → `esbl`, carbapenems → `cpe` |

No MDR cutoff, tier cutoff, prior strength or minimum count exists for evidence. The
only minimum count in the project is the weekly reporting floor used by the temporal
outlier check (§7.2), which follows the surveillance convention in the dataset README.

### 5.1 Analysis view vs full records

- **Analysis view** (`apply_surveillance`): first isolate per
  `patient_id × organism × specimen`, ordered by `sample_date, isolate_id`. Applied
  to correlations, antibiotic tier lists, ward resistance rates and outliers.
- **Full records**: used for the JSON patient/ward structure and volumes. Every
  record read in stage 1 is kept.

## 6. Correlations

Outcomes: `flag:esbl`, `flag:mrsa`, `flag:vre`, `flag:cpe`, `resistance:any`,
`resistance:antibiotic` (one stratum per antibiotic).

Predictors: `sex`, `home_area`, `ward_type`, `institution`, `ward_code`, `specimen`.

Metrics per outcome × predictor: per-group rate with Wilson 95% interval; chi-square
(no continuity correction) with p and dof; Cramér's V; min/max group rate; reference
group = largest group by n. A comparison needs ≥2 groups.

The flag and `resistance:any` outcomes pool every organism and specimen; there is no
organism stratification, so an association can be driven by case mix (Simpson's
paradox). Only `resistance:antibiotic` isolates a single agent, and it still pools
organisms.

## 7. Deviations and outliers

Two log families, both reported only:

- `consistency` — rule-based data checks (`deviations/consistency.py`,
  `deviations/plausibility.py`).
- `statistical` — funnel-plot outliers (`deviations/outliers.py`).

Neither changes the data. `unit_type` and `unit_key` only identify the record a finding
points at.

### 7.1 Consistency family

Referential and marker checks (`consistency.py`):

| Detector | Rule | Severity |
|---|---|---|
| `flag_without_marker` | positive flag with no marker susceptibility result | warning |
| `flag_susceptibility_contradiction` | positive flag but the marker result is S | critical |
| `marker_without_flag` | a definitional marker result is R but the flag is 0 | critical |
| `agent_specimen_mismatch` | `reported_for` is not "all" and the specimen differs | warning |
| `negative_culture_with_isolates` | `result="negative"` and ≥1 isolate | critical |
| `positive_culture_without_isolates` | `result="positive"` and 0 isolates | warning |
| `n_isolates_count_mismatch` | declared `n_isolates` ≠ actual rows | warning |
| `orphan_culture` / `orphan_isolate` / `orphan_susceptibility` | dangling foreign key | critical |

`marker_without_flag` only applies to `DEFINITIONAL_FLAGS = ("mrsa", "vre")`, whose
marker *is* the phenotype (cefoxitin R is the MRSA screen; vancomycin R is VRE). ESBL
and CPE are mechanism flags: cefuroxime and meropenem resistance have other mechanisms,
so a resistant marker there does not imply the flag.

Field-level plausibility checks (`plausibility.py`):

| Detector | Rule | Severity |
|---|---|---|
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

The marker mapping is a rule, but the denominator is the marker results present in
`susceptibility.csv`. `result` and `guideline` are checked as a grammar because the
dataset README declares their shape; every other plausibility rule is read from the
data (the modal label or shape of a field) or from another table.

### 7.2 Statistical family (outliers)

`deviations/outliers.py` reports funnel-plot outliers over the surveillance view. For
a cell with `n` results and `k` resistant, the rate `k/n` is compared with a reference
rate `p0` and the binomial 95% control limits
`p0 ± Z_975 · sqrt(p0(1−p0)/n)` (clamped to `[0, 1]`, `Z_975 = 1.959963984540054`).
A cell is an outlier when its rate falls outside its limits.

| Detector | Cell | Reference `p0` | Floor |
|---|---|---|---|
| `ward_rate_outlier` | `organism × antibiotic × specimen × ward_code` | same `organism × antibiotic × specimen` within the same `ward_type` | none |
| `weekly_rate_outlier` | `organism × antibiotic × specimen × iso_year/iso_week` | same `organism × antibiotic × specimen` across all weeks | cell `n ≥ 30` |

There is no multiple-comparison control, so about 5% of compared cells fall outside by
chance; the consumer filters by `n` and the cell fields. `detail` carries `n`, `k`,
`rate`, `reference_rate`, `reference_n`, `ci_low`, `ci_high` (and
`ward_code`/`ward_type` or `week`).

## 8. Evidence model (`resistance_core.TierModel`)

`TierModel` reports observed resistance only:

- `observed_resistance`, `observed_n`, Wilson interval for `organism × antibiotic ×
  specimen`, or `organism × antibiotic × specimen × ward_code` when a ward is given;
- `overall_resistance`, `overall_n`, interval for the same organism and specimen
  across all wards;
- `observed_source` is `ward` when the ward cell has data, otherwise `overall`.

Applicability: `reported_for="all"` always, `reported_for="urine"` only for urine
specimens; an antibiotic is listed only if it has specimen-specific data for the
organism. Screens are excluded unless `include_screens=True`.

No smoothing, prior, tier, minimum count or reliability label is applied.

## 9. Ward summaries (`wards.py`)

| Field | Source |
|---|---|
| `ward_fi, ward_en, ward_type, institution` | `wards.csv` |
| `date_range` | min/max `sample_date` |
| `counts` | patients, cultures, isolates, susceptibility results |
| `cultures_by_specimen`, `cultures_by_result` | all cultures |
| `organisms` | top 10 by isolate count with share |
| `flag_rates_by_organism` | per organism and flag, denominator = isolates with the marker tested, restricted to organisms where the flag is observed positive |
| `resistance_by_antibiotic` | specimen-keyed, screen-excluded list sorted by rate |
| `antibiogram` | `specimen -> organism -> [antibiotic entries]` |
| `basis` | provenance note |

## 10. JSON document (`structure.py`)

```
{
  "metadata": { source, counts, date_range, as_of, age_band_edges, settings,
                deviation_summary, outlier_summary },
  "antibiotics": [ { antibiotic, antibiotic_code, antibiotic_fi, class,
                     reported_for, role, marker_flags } ],
  "wards": { "<ward_code>": { ...see §9... } },
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
  "antibiotic_tiers": { "<organism>|<specimen>": [ { antibiotic, antibiotic_code,
      class, reported_for, role, observed_resistance, observed_n,
      observed_ci_low, observed_ci_high, observed_source, overall_resistance,
      overall_n, overall_ci_low, overall_ci_high } ] }
}
```

`deviation_summary` and `outlier_summary` share the shape
`{ total, by_family, by_severity, by_detector }`.

## 11. HTTP API

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | `{"status":"ok"}` |
| GET | `/metadata` | document metadata |
| GET | `/patients/{patient_id}` | summary + ward list |
| GET | `/patients/{patient_id}/wards/{ward_code}` | one patient × one ward |
| GET | `/wards/{ward_code}` | ward summary (§9) |
| GET | `/wards/{ward_code}/patients` | patients seen in the ward |
| GET | `/wards/{ward_code}/antibiogram` | ward evidence, `specimen`/`organism` filters |
| GET | `/patients/{patient_id}/history` | prior isolates and susceptibility |
| GET | `/antibiotics` | metadata derived from `antibiotics.csv` |
| POST | `/decision-briefs` | directed decision brief |
| GET | `/tiers/{organism}` | observed rate list; `specimen` and `ward_code` filters |
| GET | `/deviations?family=&severity=&detector=` | consistency deviation log |
| GET | `/outliers?detector=&severity=&organism=&antibiotic=&specimen=&ward_code=&week=&min_n=` | statistical outlier log |

Both logs return their `detail` as a JSON object. `/outliers` filters on the cell
fields in `detail`; `min_n` is a consumer-side filter, not a detection cutoff.

## 12. Directed decision support

`POST /decision-briefs` request:

```json
{
  "patient_id": "P...",
  "encounter": {"ward_code": "ICU", "admission_date": "<admission_date>"},
  "culture": {"organism": "Escherichia coli", "specimen": "urine", "culture_date": "<culture_date>"}
}
```

Response:

- `options` — eligible therapeutic agents sorted by observed resistance, with
  `observed_n`, interval, overall rate, `observed_source`, `rank_group` and
  warnings (`URINE_ONLY`, `PRIOR_RESISTANT`), plus prior-result fields.
- `screens` — marker results, never mixed into options.
- `excluded` — `not_reported_for_specimen` or `no_specimen_data`.
- `patient_history` — prior same-organism isolates (any specimen).
- `headline`, `context`, `period`, `data_as_of`, `limitations`.

`rank_group` groups options whose observed intervals overlap. Prior resistance uses
the most recent prior isolate of the same organism regardless of specimen.

## 13. CLI and outputs

```
uv run resistance-analysis --out output [--data-dir ...] [--all-isolates]
uv run resistance-api --dataset output/dataset.json
                      --analytics output/analytics.csv
                      --deviations output/deviations.csv
                      --outliers output/outliers.csv
```

Outputs: `dataset.json`, `analytics.csv`, `deviations.csv` / `deviations.jsonl`,
`outliers.csv` / `outliers.jsonl`, `report/correlations_summary.csv`,
`report/group_rates.csv`, `summary.md`.

## 14. Assumptions

- **A1** The data is synthetic (seed 2026).
- **A2** Susceptibility is S/R only; no I, MIC or zone diameter.
- **A3** A missing susceptibility row means "not tested", not "susceptible".
- **A4** No clinical thresholds are used. The funnel `z` is the same 1.96 the rest of
  the project uses for its Wilson intervals; it is a statistical convention, not a
  clinical rule.
- **A5** Age bands are quantiles of the observed ages; the edges are stored in the
  output and change with the dataset.
- **A6** `days_since_admission` replaces any invented "healthcare-associated" cutoff.
- **A7** `n_resistant_classes` is reported directly; no MDR cutoff is applied.
- **A8** Flag denominators come from the marker antibiotic results in
  `susceptibility.csv`, restricted to organisms where the flag is observed positive.
- **A9** Findings are reported only. A flag contradicted by a susceptible marker, and a
  definitional marker contradicted by a zero flag, are both logged; the data is never
  rewritten in either direction.
- **A10** Organism names are matched exactly; there is no taxonomy normalisation.
- **A11** The API recomputes evidence from `analytics.csv`; the JSON keeps every record.
- **A12** Outliers are reported, never applied; the ward reference is the same
  `ward_type` and the weekly reference is the whole strand.
- **A13** The weekly outlier check only compares cells with at least 30 isolates, the
  reporting floor in the dataset README. No other check applies a minimum count.

## 15. Limitations and non-goals

- The dataset has no diagnosis, dose, route, allergy, renal, severity or outcome data,
  so the system cannot determine the clinically correct antibiotic.
- Specimen is not a diagnosis.
- VRE and CPE positives are too few for stable rates.
- No authentication or pagination; this is a local exploration service.
- The marker mapping is a rule applied to data-derived denominators, not a clinical
  claim.
- Outlier detection has no multiple-comparison control, so about 5% of compared cells
  can fall outside the funnel by chance.
- The consistency checks on the supplied dataset find nothing; it is generated to be
  self-consistent.
