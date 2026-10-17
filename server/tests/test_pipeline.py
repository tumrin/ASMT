from __future__ import annotations

from dataclasses import replace

import polars as pl
from fastapi.testclient import TestClient
from resistance_analysis.config import Settings
from resistance_analysis.load import load_dataset
from resistance_analysis.pipeline import run
from resistance_api.app import create_app


def _settings(dataset_dir, tmp_path) -> Settings:
    return replace(Settings(), data_dir=dataset_dir, out_dir=tmp_path / "output")


def _client(tmp_path) -> TestClient:
    out = tmp_path / "output"
    app = create_app(out / "dataset.json", out / "deviations.csv", out / "outliers.csv")
    return TestClient(app)


def test_pipeline_writes_outputs(dataset_dir, tmp_path) -> None:
    result = run(_settings(dataset_dir, tmp_path))

    assert (tmp_path / "output" / "dataset.json").exists()
    assert (tmp_path / "output" / "analytics.csv").exists()
    assert (tmp_path / "output" / "deviations.csv").exists()
    assert (tmp_path / "output" / "outliers.csv").exists()
    assert not (tmp_path / "output" / "antibiotic_properties.json").exists()

    # Deviations are reported only; every record is kept unchanged.
    isolates = result.raw.isolates
    assert "C4-1" in isolates["isolate_id"].to_list()
    assert isolates.filter(pl.col("isolate_id") == "C5-1")["mrsa"][0] == 1
    assert isolates.filter(pl.col("isolate_id") == "C2-1")["mrsa"][0] == 1
    assert "removed" not in result.deviation_summary


def test_pipeline_does_not_change_data(dataset_dir, tmp_path) -> None:
    result = run(_settings(dataset_dir, tmp_path), write=False)
    raw = load_dataset(dataset_dir)
    doc = result.document

    assert doc["metadata"]["counts"] == {
        "patients": raw.patients.height,
        "cultures": raw.cultures.height,
        "isolates": raw.isolates.height,
        "susceptibility_results": raw.susceptibility.height,
    }

    cultures = {
        culture["culture_id"]: culture
        for patient in doc["patients"].values()
        for ward in patient["wards"].values()
        for culture in ward["cultures"]
    }
    assert set(cultures) == set(raw.cultures["culture_id"].to_list())

    isolate = next(
        isolate
        for culture in cultures.values()
        for isolate in culture["isolates"]
        if isolate["isolate_id"] == "C2-1"
    )
    assert isolate["flags"]["mrsa"] == 1
    assert isolate["susceptibility"]["cefoxitin (screen)"] == "S"


def test_document_structure_and_lookup(dataset_dir, tmp_path) -> None:
    result = run(_settings(dataset_dir, tmp_path), write=False)
    doc = result.document

    assert set(doc["patients"]) == {"P1", "P2", "P3", "P4"}

    patient = doc["patients"]["P1"]
    assert patient["patient_id"] == "P1"
    ward = patient["wards"]["MED-A"]
    culture_ids = {c["culture_id"] for c in ward["cultures"]}
    assert culture_ids == {"C1", "C5"}

    isolate = next(
        i for c in ward["cultures"] if c["culture_id"] == "C1" for i in c["isolates"]
    )
    assert isolate["organism"] == "Escherichia coli"
    assert isolate["susceptibility"]["ampicillin"] == "R"

    assert "ICU" not in patient["wards"]
    assert "NOPE" not in doc["patients"]
    assert "antibiotic_tiers" not in doc

    metadata = doc["metadata"]
    assert metadata["data_as_of"] == "2024-01-05"
    assert metadata["periods"] == ["annual:2024", "last4w"]
    assert [unit["unit"] for unit in metadata["scopes"]["ward"]] == [
        "ICU",
        "MED-A",
        "MED-B",
    ]
    assert [unit["unit"] for unit in metadata["scopes"]["region"]] == ["Centre"]
    assert metadata["settings"]["min_isolates"] == 30
    assert "as_of" not in metadata
    assert "age_band_edges" in metadata
    assert "outlier_summary" in metadata
    assert "thresholds" not in metadata

    assert "hospital|-|annual:2024" in doc["antibiogram"]


def test_api_endpoints(dataset_dir, tmp_path) -> None:
    run(_settings(dataset_dir, tmp_path))

    with _client(tmp_path) as client:
        assert client.get("/health").json() == {"status": "ok"}

        metadata = client.get("/metadata")
        assert metadata.status_code == 200
        assert metadata.json()["counts"]["patients"] == 4

        patients = client.get("/patients")
        assert patients.status_code == 200
        body = patients.json()
        assert body["n"] == 4
        assert body["patients"][0]["patient_id"] == "P1"
        assert body["patients"][0]["wards"] == ["MED-A"]

        patient = client.get("/patients/P1")
        assert patient.status_code == 200
        assert patient.json()["wards"] == ["MED-A"]

        ward = client.get("/patients/P1/wards/MED-A")
        assert ward.status_code == 200
        assert ward.json()["ward"]["ward_code"] == "MED-A"
        assert client.get("/patients/P1/wards/ICU").status_code == 404
        assert client.get("/patients/NOPE").status_code == 404

        ward_patients = client.get("/wards/MED-A/patients")
        assert ward_patients.status_code == 200
        assert ward_patients.json()["n_patients"] == 1

        ward = client.get("/wards/MED-A")
        assert ward.status_code == 200
        body = ward.json()
        assert body["ward_code"] == "MED-A"
        assert body["counts"]["cultures"] >= 1
        assert "flag_rates_by_organism" in body
        assert "antibiogram" not in body
        assert "resistance_by_antibiotic" not in body
        assert client.get("/wards/NOPE").status_code == 404

        antibiotics = client.get("/antibiotics")
        assert antibiotics.status_code == 200
        by_code = {
            entry["antibiotic_code"]: entry
            for entry in antibiotics.json()["antibiotics"]
        }
        assert by_code["FOX"]["role"] == "screen"
        assert by_code["FOX"]["marker_flags"] == ["mrsa"]

        deviations = client.get("/deviations", params={"family": "consistency"})
        assert deviations.status_code == 200
        assert deviations.json()["n"] > 0
        assert isinstance(deviations.json()["deviations"][0]["detail"], dict)

        outliers = client.get("/outliers")
        assert outliers.status_code == 200
        assert "outliers" in outliers.json()
        assert (
            client.get(
                "/outliers", params={"detector": "ward_rate_outlier"}
            ).status_code
            == 200
        )


def test_antibiogram_endpoint(dataset_dir, tmp_path) -> None:
    run(_settings(dataset_dir, tmp_path))

    with _client(tmp_path) as client:
        response = client.get(
            "/antibiogram",
            params={"scope": "hospital", "period": "annual:2024"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["scope"] == "hospital"
        assert body["period"] == "annual:2024"

        rows = {(row["organism"], row["specimen"]): row for row in body["organisms"]}
        ecoli_codes = {
            entry["antibiotic_code"]
            for entry in rows[("Escherichia coli", "urine")]["antibiotics"]
        }
        assert ecoli_codes == {"AMP", "MEC"}
        # The screen agent is excluded by default.
        aureus_codes = {
            entry["antibiotic_code"]
            for entry in rows[("Staphylococcus aureus", "blood")]["antibiotics"]
        }
        assert aureus_codes == {"VAN"}

        with_screens = client.get(
            "/antibiogram",
            params={
                "scope": "hospital",
                "period": "annual:2024",
                "specimen": "blood",
                "include_screens": True,
            },
        ).json()
        codes = {
            entry["antibiotic_code"]
            for row in with_screens["organisms"]
            for entry in row["antibiotics"]
        }
        assert codes == {"FOX", "VAN"}
        roles = {
            entry["antibiotic_code"]: entry["role"]
            for row in with_screens["organisms"]
            for entry in row["antibiotics"]
        }
        assert roles["FOX"] == "screen"

        # Ward cell counts only P1's first isolate.
        ward = client.get(
            "/antibiogram",
            params={
                "scope": "ward",
                "unit": "MED-A",
                "period": "annual:2024",
                "organism": "Escherichia coli",
            },
        ).json()
        amp = next(
            entry
            for row in ward["organisms"]
            for entry in row["antibiotics"]
            if entry["antibiotic_code"] == "AMP"
        )
        assert amp["n"] == 1
        assert amp["susceptibility_rate"] is None
        assert amp["traffic_light"] == "none"

        assert (
            client.get(
                "/antibiogram", params={"scope": "ward", "unit": "NOPE"}
            ).status_code
            == 404
        )


def test_recommendation_endpoint(dataset_dir, tmp_path) -> None:
    run(_settings(dataset_dir, tmp_path))

    with _client(tmp_path) as client:
        response = client.get(
            "/recommendations",
            params={
                "scope": "ward",
                "unit": "MED-A",
                "organism": "Escherichia coli",
                "specimen": "urine",
            },
        )
        assert response.status_code == 200
        body = response.json()
        codes = [entry["antibiotic_code"] for entry in body["options"]]
        assert codes == ["AMP", "MEC"]
        assert all(entry["susceptibility_rate"] is None for entry in body["options"])
        assert all(entry["traffic_light"] == "none" for entry in body["options"])
        # No reportable ward cell, so the rate falls back to the ward last4w base.
        assert body["options"][0]["source_scope"] == "ward"
        assert body["options"][0]["source_period"] == "last4w"

        excluded = {entry["antibiotic_code"]: entry for entry in body["excluded"]}
        assert excluded["VAN"]["reason"] == "no_specimen_data"
        assert "FOX" not in excluded
        assert body["data_as_of"] == "2024-01-05"
