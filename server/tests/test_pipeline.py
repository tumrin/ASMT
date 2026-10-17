from __future__ import annotations

import json
from dataclasses import replace

import polars as pl
from fastapi.testclient import TestClient
from resistance_analysis.config import Settings
from resistance_analysis.load import load_dataset
from resistance_analysis.pipeline import run
from resistance_api.app import create_app


def _settings(dataset_dir, tmp_path) -> Settings:
    return replace(Settings(), data_dir=dataset_dir, out_dir=tmp_path / "output")


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
    assert "Escherichia coli|urine" in doc["antibiotic_tiers"]

    metadata = doc["metadata"]
    assert "age_band_edges" in metadata
    assert "outlier_summary" in metadata
    assert "thresholds" not in metadata
    assert "recent_months" not in metadata
    assert (
        "mdr"
        not in next(iter(doc["patients"]["P1"]["wards"]["MED-A"]["cultures"]))[
            "isolates"
        ][0]
    )


def test_api_endpoints(dataset_dir, tmp_path) -> None:
    run(_settings(dataset_dir, tmp_path))
    out = tmp_path / "output"
    app = create_app(
        out / "dataset.json", out / "analytics.csv", out / "deviations.csv"
    )

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}

        metadata = client.get("/metadata")
        assert metadata.status_code == 200
        assert metadata.json()["counts"]["patients"] == 4

        patient = client.get("/patients/P1")
        assert patient.status_code == 200
        assert patient.json()["wards"] == ["MED-A"]

        ward = client.get("/patients/P1/wards/MED-A")
        assert ward.status_code == 200
        assert ward.json()["ward"]["ward_code"] == "MED-A"
        assert client.get("/patients/P1/wards/ICU").status_code == 404
        assert client.get("/patients/NOPE").status_code == 404

        patients = client.get("/wards/MED-A/patients")
        assert patients.status_code == 200
        assert patients.json()["n_patients"] == 1

        ward = client.get("/wards/MED-A")
        assert ward.status_code == 200
        body = ward.json()
        assert body["ward_code"] == "MED-A"
        assert body["counts"]["cultures"] >= 1
        assert "flag_rates_by_organism" in body
        assert "urine" in body["resistance_by_antibiotic"]
        assert client.get("/wards/NOPE").status_code == 404

        tiers = client.get(
            "/tiers/Escherichia coli",
            params={"specimen": "urine"},
        )
        assert tiers.status_code == 200
        body = tiers.json()
        codes = {entry["antibiotic_code"] for entry in body["tiers"]}
        assert codes >= {"AMP", "MEC"}
        assert "predicted_resistance" not in body["tiers"][0]

        all_specimens = client.get("/tiers/Escherichia coli")
        assert all_specimens.status_code == 200
        assert "urine" in all_specimens.json()["tiers"]

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


def test_decision_brief_endpoint(dataset_dir, tmp_path) -> None:
    run(_settings(dataset_dir, tmp_path))
    out = tmp_path / "output"
    app = create_app(
        out / "dataset.json", out / "analytics.csv", out / "deviations.csv"
    )
    with TestClient(app) as client:
        response = client.post(
            "/decision-briefs",
            json={
                "patient_id": "P1",
                "encounter": {"ward_code": "MED-A"},
                "culture": {
                    "organism": "Escherichia coli",
                    "specimen": "urine",
                    "culture_date": "2024-01-05",
                },
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["context"]["ward_code"] == "MED-A"
        codes = [entry["antibiotic_code"] for entry in body["options"]]
        assert codes == ["MEC", "AMP"]
        assert body["options"][0]["observed_resistance"] == 0.0
        assert body["options"][1]["prior_result"] == "R"
        assert "insufficient_evidence" not in body
        assert body["period"]["start"] == "2024-01-01"


def test_decision_brief_reports_screens_and_history(dataset_dir, tmp_path) -> None:
    isolates = pl.read_csv(dataset_dir / "isolates.csv").with_columns(
        pl.when(pl.col("isolate_id") == "C2-1")
        .then(0)
        .otherwise(pl.col("mrsa"))
        .alias("mrsa")
    )
    isolates.write_csv(dataset_dir / "isolates.csv")

    run(_settings(dataset_dir, tmp_path))
    out = tmp_path / "output"
    app = create_app(
        out / "dataset.json", out / "analytics.csv", out / "deviations.csv"
    )
    with TestClient(app) as client:
        response = client.post(
            "/decision-briefs",
            json={
                "patient_id": "P2",
                "encounter": {"ward_code": "ICU"},
                "culture": {
                    "organism": "Staphylococcus aureus",
                    "specimen": "blood",
                    "culture_date": "2024-01-02",
                },
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert {entry["antibiotic_code"] for entry in body["options"]} == {"VAN"}
        assert body["screens"] == [
            {
                "antibiotic": "cefoxitin (screen)",
                "antibiotic_code": "FOX",
                "result": "S",
                "interpretation": "screen negative",
            }
        ]

        history = client.get(
            "/patients/P1/history", params={"organism": "Escherichia coli"}
        )
        assert history.status_code == 200
        assert len(history.json()["history"]) == 2

        antibiotics = client.get("/antibiotics")
        assert antibiotics.status_code == 200
        by_code = {
            entry["antibiotic_code"]: entry
            for entry in antibiotics.json()["antibiotics"]
        }
        assert by_code["FOX"]["role"] == "screen"
        assert by_code["FOX"]["marker_flags"] == ["mrsa"]
        assert "routes" not in by_code["FOX"]


def test_ward_antibiogram_endpoint(dataset_dir, tmp_path) -> None:
    run(_settings(dataset_dir, tmp_path))
    out = tmp_path / "output"
    app = create_app(
        out / "dataset.json", out / "analytics.csv", out / "deviations.csv"
    )
    with TestClient(app) as client:
        response = client.get(
            "/wards/MED-A/antibiogram",
            params={"specimen": "urine", "organism": "Escherichia coli"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ward_code"] == "MED-A"
        entries = body["specimens"]["urine"]["Escherichia coli"]
        assert {entry["antibiotic_code"] for entry in entries} >= {"AMP", "MEC"}
        assert all(entry["role"] != "screen" for entry in entries)
        assert client.get("/wards/NOPE/antibiogram").status_code == 404


def test_written_json_is_valid(dataset_dir, tmp_path) -> None:
    run(_settings(dataset_dir, tmp_path))
    doc = json.loads((tmp_path / "output" / "dataset.json").read_text(encoding="utf-8"))
    assert "metadata" in doc and "patients" in doc and "antibiotic_tiers" in doc
    assert "marker_flags" in doc["antibiotics"][0]
    assert "routes" not in doc["antibiotics"][0]
