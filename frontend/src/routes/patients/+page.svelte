<script lang="ts">
    import { onMount } from "svelte";

    type Sex = "F" | "M";
    type TrafficLight = "green" | "yellow" | "red" | "none";

    type PatientSummary = {
        patient_id: string;
        sex: Sex;
        birth_year: number;
        home_area: string;
        ward: string;
        ward_code: string;
        admission_date?: string;
    };

    type CultureFinding = {
        culture_id: string;
        sample_date: string;
        specimen: string;
        result: string;
        organism: string;
        flags: string[];
        susceptibility: Record<string, string>;
    };

    type Recommendation = {
        antibiotic: string;
        susceptibility_rate: number | null;
        traffic_light: TrafficLight;
        n: number;
        source: string;
        note: string;
    };

    type PatientDetail = {
        patient_id: string;
        sex: Sex;
        birth_year: number;
        home_area: string;
        current_ward: string;
        admission_date: string;
        cultures: CultureFinding[];
        recommendations: Recommendation[];
    };

    const mockPatients: PatientSummary[] = [
        {
            patient_id: "PT-1001",
            sex: "F",
            birth_year: 1988,
            home_area: "North",
            ward: "Internal Medicine A",
            ward_code: "MED-A",
            admission_date: "2026-10-01",
        },
        {
            patient_id: "PT-1002",
            sex: "M",
            birth_year: 1974,
            home_area: "South",
            ward: "Surgery",
            ward_code: "SURG",
            admission_date: "2026-09-26",
        },
        {
            patient_id: "PT-1003",
            sex: "F",
            birth_year: 1967,
            home_area: "North",
            ward: "Urology",
            ward_code: "URO",
            admission_date: "2026-10-05",
        },
    ];

    const mockDetails: Record<string, PatientDetail> = {
        "PT-1001": {
            patient_id: "PT-1001",
            sex: "F",
            birth_year: 1988,
            home_area: "North",
            current_ward: "Internal Medicine A",
            admission_date: "2026-10-01",
            cultures: [
                {
                    culture_id: "C-1104",
                    sample_date: "2026-10-08",
                    specimen: "urine",
                    result: "positive",
                    organism: "Escherichia coli",
                    flags: ["ESBL"],
                    susceptibility: {
                        ampicillin: "R",
                        mecillinam: "S",
                        trimethoprim: "R",
                        nitrofurantoin: "S",
                    },
                },
                {
                    culture_id: "C-1152",
                    sample_date: "2026-10-12",
                    specimen: "blood",
                    result: "positive",
                    organism: "Staphylococcus aureus",
                    flags: ["MRSA"],
                    susceptibility: {
                        vancomycin: "S",
                        clindamycin: "R",
                        ciprofloxacin: "R",
                    },
                },
            ],
            recommendations: [
                {
                    antibiotic: "mecillinam",
                    susceptibility_rate: 92,
                    traffic_light: "green",
                    n: 84,
                    source: "ward / last4w",
                    note: "Best match for urine E. coli in this ward.",
                },
                {
                    antibiotic: "nitrofurantoin",
                    susceptibility_rate: 88,
                    traffic_light: "green",
                    n: 71,
                    source: "hospital / annual:2026",
                    note: "Useful urinary option with high cumulative susceptibility.",
                },
                {
                    antibiotic: "trimethoprim",
                    susceptibility_rate: 52,
                    traffic_light: "red",
                    n: 63,
                    source: "hospital / last4w",
                    note: "Not recommended because this isolate has prior resistance.",
                },
            ],
        },
        "PT-1002": {
            patient_id: "PT-1002",
            sex: "M",
            birth_year: 1974,
            home_area: "South",
            current_ward: "Surgery",
            admission_date: "2026-09-26",
            cultures: [
                {
                    culture_id: "C-2103",
                    sample_date: "2026-09-28",
                    specimen: "wound",
                    result: "positive",
                    organism: "Pseudomonas aeruginosa",
                    flags: ["CPE"],
                    susceptibility: {
                        piperacillin_tazobactam: "S",
                        ciprofloxacin: "R",
                        meropenem: "S",
                    },
                },
            ],
            recommendations: [
                {
                    antibiotic: "meropenem",
                    susceptibility_rate: 88,
                    traffic_light: "green",
                    n: 59,
                    source: "hospital / annual:2026",
                    note: "Highest cumulative activity against this organism.",
                },
                {
                    antibiotic: "piperacillin-tazobactam",
                    susceptibility_rate: 74,
                    traffic_light: "yellow",
                    n: 45,
                    source: "ward / annual:2026",
                    note: "Reasonable compromise option, subject to local susceptibility.",
                },
            ],
        },
        "PT-1003": {
            patient_id: "PT-1003",
            sex: "F",
            birth_year: 1967,
            home_area: "North",
            current_ward: "Urology",
            admission_date: "2026-10-05",
            cultures: [
                {
                    culture_id: "C-3011",
                    sample_date: "2026-10-07",
                    specimen: "urine",
                    result: "positive",
                    organism: "Escherichia coli",
                    flags: [],
                    susceptibility: {
                        ampicillin: "S",
                        mecillinam: "S",
                        trimethoprim: "S",
                        nitrofurantoin: "S",
                    },
                },
            ],
            recommendations: [
                {
                    antibiotic: "nitrofurantoin",
                    susceptibility_rate: 93,
                    traffic_light: "green",
                    n: 77,
                    source: "hospital / last4w",
                    note: "Strong local activity for uncomplicated urinary E. coli.",
                },
                {
                    antibiotic: "mecillinam",
                    susceptibility_rate: 90,
                    traffic_light: "green",
                    n: 82,
                    source: "hospital / annual:2026",
                    note: "Another appropriate urinary therapy option.",
                },
            ],
        },
    };

    let patients = $state<PatientSummary[]>([]);
    let selectedPatientId = $state<string>("");
    let status = $state<string>("Loading patient list...");
    let statusTone = $state<"info" | "error">("info");
    let searchTerm = $state<string>("");

    const trafficLightMeta: Record<
        TrafficLight,
        { label: string; color: string }
    > = {
        green: { label: "Green", color: "#1f9d61" },
        yellow: { label: "Yellow", color: "#d29a00" },
        red: { label: "Red", color: "#cf3b3b" },
        none: { label: "None", color: "#5b6470" },
    };

    const filteredPatients = $derived.by(() => {
        const term = searchTerm.trim().toLowerCase();
        if (!term) return patients;
        return patients.filter((patient) => {
            return (
                patient.patient_id.toLowerCase().includes(term) ||
                patient.ward.toLowerCase().includes(term) ||
                patient.home_area.toLowerCase().includes(term)
            );
        });
    });

    const selectedPatient = $derived.by(() => {
        const patient = patients.find(
            (item) => item.patient_id === selectedPatientId,
        );
        if (patient) {
            return patient;
        }
        return patients[0] ?? null;
    });

    const selectedDetail = $derived.by(() => {
        const patientId = selectedPatient?.patient_id ?? selectedPatientId;
        return mockDetails[patientId] ?? null;
    });

    const age = (birthYear: number) => new Date().getFullYear() - birthYear;

    async function loadPatientList() {
        try {
            const response = await fetch("http://127.0.0.1:8000/patients");
            if (!response.ok) {
                throw new Error(`Backend responded with ${response.status}`);
            }
            const payload = (await response.json()) as {
                items?: PatientSummary[];
            };
            const items =
                Array.isArray(payload.items) && payload.items.length > 0
                    ? payload.items
                    : mockPatients;
            patients = items;
            status = "Live backend data is available.";
            statusTone = "info";
        } catch (error) {
            console.warn(
                "Patient endpoint unavailable yet. Showing mock patient data.",
                error,
            );
            patients = mockPatients;
            status =
                "Backend endpoint is not implemented yet; showing sample patient data.";
            statusTone = "error";
        }

        if (!selectedPatientId && patients.length > 0) {
            selectedPatientId = patients[0].patient_id;
        }
    }

    onMount(() => {
        loadPatientList();
    });

    $effect(() => {
        if (!selectedPatientId && patients.length > 0) {
            selectedPatientId = patients[0].patient_id;
        }
    });
</script>

<svelte:head>
    <title>Patient view</title>
</svelte:head>

<div class="page-shell">
    <header class="topbar">
        <div>
            <h1>Patient view</h1>
            <p>
                Review patient details, recent cultures and local antibiotic
                recommendations.
            </p>
        </div>
        <a class="nav-link" href="/">Back to overview</a>
    </header>

    <div class={`status-banner ${statusTone}`}>
        {status}
    </div>

    <div class="layout">
        <aside class="panel patient-list-panel">
            <div class="panel-header">
                <h2>Patients</h2>
                <input
                    bind:value={searchTerm}
                    type="search"
                    placeholder="Search patient, ward or area"
                    aria-label="Search patient list"
                />
            </div>

            {#if filteredPatients.length === 0}
                <p class="empty-state">No patients match the current search.</p>
            {:else}
                <ul class="patient-list">
                    {#each filteredPatients as patient}
                        <li>
                            <button
                                type="button"
                                class:active={selectedPatient?.patient_id ===
                                    patient.patient_id}
                                onclick={() =>
                                    (selectedPatientId = patient.patient_id)}
                            >
                                <div class="patient-id">
                                    {patient.patient_id}
                                </div>
                                <div class="patient-meta">
                                    {patient.sex} · {age(patient.birth_year)} yrs
                                </div>
                                <div class="patient-meta">{patient.ward}</div>
                            </button>
                        </li>
                    {/each}
                </ul>
            {/if}
        </aside>

        <main class="panel patient-detail-panel">
            {#if selectedPatient && selectedDetail}
                <section class="summary-grid">
                    <div class="summary-card">
                        <span class="label">Patient ID</span>
                        <strong>{selectedDetail.patient_id}</strong>
                    </div>
                    <div class="summary-card">
                        <span class="label">Sex</span>
                        <strong>{selectedDetail.sex}</strong>
                    </div>
                    <div class="summary-card">
                        <span class="label">Age</span>
                        <strong>{age(selectedDetail.birth_year)} years</strong>
                    </div>
                    <div class="summary-card">
                        <span class="label">Home area</span>
                        <strong>{selectedDetail.home_area}</strong>
                    </div>
                    <div class="summary-card">
                        <span class="label">Current ward</span>
                        <strong>{selectedDetail.current_ward}</strong>
                    </div>
                    <div class="summary-card">
                        <span class="label">Admission</span>
                        <strong>{selectedDetail.admission_date}</strong>
                    </div>
                </section>

                <section class="section-block">
                    <div class="section-header">
                        <h2>Culture history</h2>
                    </div>
                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th>Date</th>
                                    <th>Specimen</th>
                                    <th>Organism</th>
                                    <th>Result</th>
                                    <th>Resistance markers</th>
                                    <th>Susceptibility</th>
                                </tr>
                            </thead>
                            <tbody>
                                {#each selectedDetail.cultures as culture}
                                    <tr>
                                        <td>{culture.sample_date}</td>
                                        <td>{culture.specimen}</td>
                                        <td>{culture.organism}</td>
                                        <td>{culture.result}</td>
                                        <td>
                                            {#if culture.flags.length === 0}
                                                <span class="muted">None</span>
                                            {:else}
                                                {#each culture.flags as flag}
                                                    <span class="flag"
                                                        >{flag}</span
                                                    >
                                                {/each}
                                            {/if}
                                        </td>
                                        <td>
                                            {#each Object.entries(culture.susceptibility) as [agent, outcome]}
                                                <span
                                                    class="susceptibility-pill {outcome.toLowerCase()}"
                                                    >{agent}: {outcome}</span
                                                >
                                            {/each}
                                        </td>
                                    </tr>
                                {/each}
                            </tbody>
                        </table>
                    </div>
                </section>

                <section class="section-block">
                    <div class="section-header">
                        <h2>Empiric recommendations</h2>
                        <p>
                            Decision support only; history is shown for context
                            and does not affect the recommendation.
                        </p>
                    </div>
                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th>Antibiotic</th>
                                    <th>Rate</th>
                                    <th>n</th>
                                    <th>Traffic light</th>
                                    <th>Source</th>
                                    <th>Note</th>
                                </tr>
                            </thead>
                            <tbody>
                                {#each selectedDetail.recommendations as recommendation}
                                    <tr>
                                        <td>{recommendation.antibiotic}</td>
                                        <td>
                                            {recommendation.susceptibility_rate ==
                                            null
                                                ? "–"
                                                : `${recommendation.susceptibility_rate}%`}
                                        </td>
                                        <td>{recommendation.n}</td>
                                        <td>
                                            <span
                                                class="traffic-pill"
                                                style={`background:${trafficLightMeta[recommendation.traffic_light].color}`}
                                            >
                                                {trafficLightMeta[
                                                    recommendation.traffic_light
                                                ].label}
                                            </span>
                                        </td>
                                        <td>{recommendation.source}</td>
                                        <td>{recommendation.note}</td>
                                    </tr>
                                {/each}
                            </tbody>
                        </table>
                    </div>
                </section>
            {:else}
                <p class="empty-state">
                    Choose a patient from the list to inspect their record.
                </p>
            {/if}
        </main>
    </div>
</div>

<style>
    :global(body) {
        margin: 0;
        font-family: Inter, "Segoe UI", sans-serif;
        background: #f4f7fb;
        color: #122033;
    }

    * {
        box-sizing: border-box;
    }

    .page-shell {
        max-width: 1400px;
        margin: 0 auto;
        padding: 2rem 1.5rem 3rem;
    }

    .topbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        margin-bottom: 1rem;
    }

    .topbar h1 {
        margin: 0;
        font-size: clamp(2rem, 3vw, 2.9rem);
    }

    .topbar p {
        margin: 0.45rem 0 0;
        color: #4f6278;
    }

    .nav-link {
        color: #123b7a;
        text-decoration: none;
        font-weight: 600;
        padding: 0.7rem 1rem;
        border-radius: 999px;
        background: #e8f0ff;
    }

    .status-banner {
        margin-bottom: 1.5rem;
        padding: 0.8rem 1rem;
        border-radius: 10px;
        font-weight: 600;
        border: 1px solid #dfe7f3;
    }

    .status-banner.info {
        background: #edf7ff;
        color: #174f8d;
    }

    .status-banner.error {
        background: #fff3f3;
        color: #8d2c2c;
    }

    .layout {
        display: grid;
        grid-template-columns: minmax(270px, 340px) minmax(0, 1fr);
        gap: 1.25rem;
        align-items: start;
    }

    .panel {
        background: #ffffff;
        border: 1px solid #dfe7f3;
        border-radius: 16px;
        box-shadow: 0 8px 22px rgba(34, 63, 94, 0.06);
    }

    .patient-list-panel {
        padding: 1rem;
    }

    .panel-header {
        display: flex;
        flex-direction: column;
        gap: 0.65rem;
        margin-bottom: 0.9rem;
    }

    .panel-header h2,
    .section-header h2 {
        margin: 0;
    }

    .panel-header input {
        width: 100%;
        padding: 0.7rem 0.8rem;
        border: 1px solid #d8e2f0;
        border-radius: 10px;
        font: inherit;
    }

    .patient-list {
        list-style: none;
        padding: 0;
        margin: 0;
        display: grid;
        gap: 0.75rem;
    }

    .patient-list button {
        width: 100%;
        text-align: left;
        padding: 0.85rem 0.9rem;
        border: 1px solid #dfe7f3;
        border-radius: 12px;
        background: #f8fbff;
        cursor: pointer;
        transition: all 0.15s ease;
    }

    .patient-list button:hover,
    .patient-list button.active {
        border-color: #7ca7ff;
        background: #edf4ff;
    }

    .patient-id {
        font-size: 1.05rem;
        font-weight: 700;
    }

    .patient-meta {
        margin-top: 0.2rem;
        color: #52657f;
        font-size: 0.9rem;
    }

    .patient-detail-panel {
        padding: 1.2rem;
    }

    .summary-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 0.9rem;
        margin-bottom: 1.2rem;
    }

    .summary-card {
        padding: 0.9rem 1rem;
        border: 1px solid #dfe7f3;
        border-radius: 12px;
        background: #f9fbff;
    }

    .label {
        display: block;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #607087;
        margin-bottom: 0.3rem;
    }

    .section-block {
        margin-top: 1.2rem;
    }

    .section-header {
        display: flex;
        justify-content: space-between;
        align-items: end;
        gap: 1rem;
        margin-bottom: 0.7rem;
    }

    .section-header p {
        margin: 0;
        color: #5a6d86;
        font-size: 0.92rem;
    }

    .table-wrap {
        overflow-x: auto;
    }

    table {
        width: 100%;
        border-collapse: collapse;
        min-width: 760px;
    }

    th,
    td {
        padding: 0.8rem 0.7rem;
        border-bottom: 1px solid #e5ebf4;
        text-align: left;
        vertical-align: top;
    }

    th {
        font-size: 0.8rem;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: #4f647d;
        background: #f7faff;
    }

    .flag,
    .susceptibility-pill,
    .traffic-pill {
        display: inline-flex;
        align-items: center;
        padding: 0.22rem 0.5rem;
        border-radius: 999px;
        font-size: 0.76rem;
        font-weight: 600;
    }

    .flag {
        background: #edf3ff;
        color: #203f79;
        margin-right: 0.35rem;
        margin-bottom: 0.2rem;
    }

    .susceptibility-pill {
        margin: 0 0.3rem 0.3rem 0;
        background: #eef4f9;
        color: #213d5f;
    }

    .susceptibility-pill.s {
        background: #eafaf2;
        color: #156a42;
    }

    .susceptibility-pill.r {
        background: #fff0f0;
        color: #9d2f2f;
    }

    .traffic-pill {
        color: white;
        padding-inline: 0.7rem;
    }

    .muted {
        color: #6c7d91;
    }

    .empty-state {
        padding: 1rem;
        border: 1px dashed #cbd6e8;
        border-radius: 12px;
        color: #51657d;
        background: #fafcff;
    }

    @media (max-width: 920px) {
        .layout {
            grid-template-columns: 1fr;
        }

        .topbar {
            flex-direction: column;
            align-items: flex-start;
        }
    }
</style>
