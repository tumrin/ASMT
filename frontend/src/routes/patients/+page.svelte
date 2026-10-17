<script lang="ts">
    import { onMount } from "svelte";

    type PatientListItem = {
        patient_id: string;
        sex: string;
        birth_year: number;
        home_area: string;
        wards: string[];
    };

    type PatientSummary = {
        patient_id: string;
        sex: string;
        birth_year: number;
        home_area: string;
        wards: string[];
    };

    type WardIsolate = {
        isolate_id: string;
        isolate_no: number;
        organism: string;
        quantity: string | null;
        flags: {
            esbl: number;
            mrsa: number;
            vre: number;
            cpe: number;
        };
        susceptibility: Record<string, string>;
    };

    type WardCulture = {
        culture_id: string;
        sample_date: string;
        iso_year: number;
        iso_week: number;
        age_years: number;
        specimen: string;
        result: string;
        n_isolates: number;
        days_since_admission: number | null;
        isolates: WardIsolate[];
    };

    type WardDetail = {
        ward_code: string;
        ward_fi: string | null;
        ward_en: string | null;
        ward_type: string | null;
        institution: string | null;
        cultures: WardCulture[];
    };

    type HistoryEntry = {
        isolate_id: string;
        culture_id: string;
        organism: string;
        specimen: string;
        ward_code: string | null;
        sample_date: string | null;
        days_ago: number | null;
        flags: {
            esbl: number;
            mrsa: number;
            vre: number;
            cpe: number;
        };
        susceptibility: Record<string, string>;
    };

    type RecommendationOption = {
        antibiotic: string;
        antibiotic_code: string;
        class: string;
        reported_for: string;
        role: string;
        n: number;
        n_s: number;
        susceptibility_rate: number | null;
        ci_low: number | null;
        ci_high: number | null;
        traffic_light: string;
        source_scope: string;
        source_unit: string;
        source_period: string;
    };

    type RecommendationResponse = {
        scope: string;
        unit: string;
        organism: string;
        specimen: string;
        data_as_of: string | null;
        options: RecommendationOption[];
        excluded: Array<{ antibiotic: string; reason: string; detail: string }>;
        limitations: string[];
    };

    type RecommendationGroup = {
        organism: string;
        specimen: string;
        options: RecommendationOption[];
    };

    const API_BASE = "http://127.0.0.1:8000";

    let patientList = $state<PatientListItem[]>([]);
    let patientSummary = $state<PatientSummary | null>(null);
    let selectedPatientId = $state<string>("");
    let selectedWard = $state<string>("");
    let wardDocument = $state<WardDetail | null>(null);
    let history = $state<HistoryEntry[]>([]);
    let recommendationGroups = $state<RecommendationGroup[]>([]);
    let status = $state<string>("Loading patient list...");
    let statusTone = $state<"info" | "error">("info");
    let searchTerm = $state<string>("");
    let loading = $state(false);
    let selectionVersion = 0;

    const filteredPatients = $derived.by(() => {
        const term = searchTerm.trim().toLowerCase();
        if (!term) return patientList;

        return patientList.filter((patient) => {
            const wardText = patient.wards.join(" ").toLowerCase();
            return (
                patient.patient_id.toLowerCase().includes(term) ||
                wardText.includes(term) ||
                patient.home_area.toLowerCase().includes(term)
            );
        });
    });

    const uniqueOrganismSpecimens = $derived.by(() => {
        const map = new Map<string, { organism: string; specimen: string }>();
        for (const entry of history) {
            const key = `${entry.organism}::${entry.specimen}`;
            if (!map.has(key)) {
                map.set(key, {
                    organism: entry.organism,
                    specimen: entry.specimen,
                });
            }
        }
        return [...map.values()];
    });

    const age = (birthYear: number) => new Date().getFullYear() - birthYear;

    function flagList(flags: {
        esbl: number;
        mrsa: number;
        vre: number;
        cpe: number;
    }): string[] {
        const list: string[] = [];
        if (flags.esbl) list.push("ESBL");
        if (flags.mrsa) list.push("MRSA");
        if (flags.vre) list.push("VRE");
        if (flags.cpe) list.push("CPE");
        return list;
    }

    async function fetchJson<T>(url: string): Promise<T> {
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`Request failed (${response.status}) for ${url}`);
        }
        return (await response.json()) as T;
    }

    async function loadPatientList() {
        loading = true;
        try {
            const payload = await fetchJson<{
                n: number;
                patients: PatientListItem[];
            }>(`${API_BASE}/patients`);
            patientList = payload.patients ?? [];
            status = `Loaded ${patientList.length} patients.`;
            statusTone = "info";

            if (patientList.length > 0 && !selectedPatientId) {
                selectedPatientId = patientList[0].patient_id;
                await selectPatient(patientList[0].patient_id);
            }
        } catch (error) {
            console.error(error);
            status = "Failed to load patients from the backend.";
            statusTone = "error";
        } finally {
            loading = false;
        }
    }

    async function loadWardDocument(patientId: string, wardCode: string) {
        const payload = await fetchJson<{
            patient: PatientSummary;
            ward: WardDetail;
        }>(`${API_BASE}/patients/${patientId}/wards/${wardCode}`);
        return payload.ward;
    }

    async function loadHistory(patientId: string) {
        const payload = await fetchJson<{
            patient_id: string;
            organism: string | null;
            history: HistoryEntry[];
        }>(`${API_BASE}/patients/${patientId}/history`);
        return payload.history ?? [];
    }

    async function loadRecommendationsForFinding(
        wardCode: string,
        organism: string,
        specimen: string,
    ) {
        const url = `${API_BASE}/recommendations?scope=ward&unit=${encodeURIComponent(wardCode)}&organism=${encodeURIComponent(organism)}&specimen=${encodeURIComponent(specimen)}&period=last4w`;
        const payload = await fetchJson<RecommendationResponse>(url);
        return {
            organism,
            specimen,
            options: payload.options ?? [],
        } satisfies RecommendationGroup;
    }

    async function refreshRecommendations() {
        const patientId = selectedPatientId;
        const wardCode = selectedWard;
        if (
            !selectedPatientId ||
            !selectedWard ||
            uniqueOrganismSpecimens.length === 0
        ) {
            recommendationGroups = [];
            return;
        }

        const findings = await Promise.all(
            uniqueOrganismSpecimens.map(({ organism, specimen }) =>
                loadRecommendationsForFinding(selectedWard, organism, specimen),
            ),
        );

        if (selectedPatientId !== patientId || selectedWard !== wardCode)
            return;
        recommendationGroups = findings.filter(
            (item) => item.options.length > 0,
        );
    }

    async function selectPatient(patientId: string) {
        const requestVersion = ++selectionVersion;
        selectedPatientId = patientId;
        searchTerm = "";
        patientSummary = null;
        selectedWard = "";
        wardDocument = null;
        history = [];
        recommendationGroups = [];
        loading = true;
        try {
            const summary = await fetchJson<PatientSummary>(
                `${API_BASE}/patients/${patientId}`,
            );
            if (requestVersion !== selectionVersion) return;
            patientSummary = summary;

            const wardChoices = summary.wards ?? [];
            selectedWard = wardChoices[0] ?? "";

            const [ward, patientHistory] = await Promise.all([
                selectedWard ? loadWardDocument(patientId, selectedWard) : null,
                loadHistory(patientId),
            ]);
            if (requestVersion !== selectionVersion) return;
            wardDocument = ward;
            history = patientHistory;
            await refreshRecommendations();
            status = `Loaded patient ${patientId}.`;
            statusTone = "info";
        } catch (error) {
            if (requestVersion !== selectionVersion) return;
            console.error(error);
            status = `Unable to load patient ${patientId}.`;
            statusTone = "error";
        } finally {
            if (requestVersion === selectionVersion) loading = false;
        }
    }

    async function selectWard(wardCode: string) {
        const patientId = selectedPatientId;
        selectedWard = wardCode;
        wardDocument = null;
        loading = true;
        try {
            const ward = await loadWardDocument(patientId, wardCode);
            if (selectedPatientId !== patientId || selectedWard !== wardCode)
                return;
            wardDocument = ward;
            await refreshRecommendations();
        } catch (error) {
            if (selectedPatientId !== patientId || selectedWard !== wardCode)
                return;
            console.error(error);
            status = `Unable to load ward ${wardCode}.`;
            statusTone = "error";
        } finally {
            if (selectedPatientId === patientId && selectedWard === wardCode) {
                loading = false;
            }
        }
    }

    onMount(() => {
        void loadPatientList();
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
                Review patient details, recent cultures and local
                recommendations.
            </p>
        </div>
        <a class="nav-link" href="/">Back to overview</a>
    </header>

    <div class={`status-banner ${statusTone}`}>
        {loading ? "Loading patient data..." : status}
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
                                class:active={selectedPatientId ===
                                    patient.patient_id}
                                onclick={() =>
                                    void selectPatient(patient.patient_id)}
                            >
                                <div class="patient-id">
                                    {patient.patient_id}
                                </div>
                                <div class="patient-meta">
                                    {patient.sex} · {age(patient.birth_year)} yrs
                                </div>
                                <div class="patient-meta">
                                    {patient.wards.join(", ") || "No ward data"}
                                </div>
                            </button>
                        </li>
                    {/each}
                </ul>
            {/if}
        </aside>

        <main class="panel patient-detail-panel">
            {#if patientSummary}
                <section class="summary-grid">
                    <div class="summary-card">
                        <span class="label">Patient ID</span>
                        <strong>{patientSummary.patient_id}</strong>
                    </div>
                    <div class="summary-card">
                        <span class="label">Sex</span>
                        <strong>{patientSummary.sex}</strong>
                    </div>
                    <div class="summary-card">
                        <span class="label">Age</span>
                        <strong>{age(patientSummary.birth_year)} years</strong>
                    </div>
                    <div class="summary-card">
                        <span class="label">Home area</span>
                        <strong>{patientSummary.home_area}</strong>
                    </div>
                    <div class="summary-card">
                        <span class="label">Wards</span>
                        <strong>{patientSummary.wards.join(", ") || "—"}</strong
                        >
                    </div>
                    <div class="summary-card">
                        <span class="label">Selected ward</span>
                        <strong>{selectedWard || "—"}</strong>
                    </div>
                </section>

                {#if patientSummary.wards.length > 0}
                    <div class="ward-picker">
                        <label for="ward-select">Ward</label>
                        <select
                            id="ward-select"
                            bind:value={selectedWard}
                            onchange={() => void selectWard(selectedWard)}
                        >
                            {#each patientSummary.wards as wardCode}
                                <option value={wardCode}>{wardCode}</option>
                            {/each}
                        </select>
                    </div>
                {/if}

                {#if wardDocument}
                    <section class="section-block">
                        <div class="section-header">
                            <h2>Ward cultures</h2>
                            <p>
                                {wardDocument.ward_fi ??
                                    wardDocument.ward_en ??
                                    wardDocument.ward_code}
                            </p>
                        </div>
                        <div class="table-wrap">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Date</th>
                                        <th>Specimen</th>
                                        <th>Result</th>
                                        <th>Isolates</th>
                                        <th>Resistance markers</th>
                                        <th>Susceptibility</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {#each wardDocument.cultures as culture}
                                        <tr>
                                            <td>{culture.sample_date}</td>
                                            <td>{culture.specimen}</td>
                                            <td>{culture.result}</td>
                                            <td>
                                                {#if culture.isolates.length === 0}
                                                    <span class="muted">—</span>
                                                {:else}
                                                    {#each culture.isolates as isolate}
                                                        <div
                                                            class="isolate-line"
                                                        >
                                                            <strong
                                                                >{isolate.organism}</strong
                                                            >
                                                            <span
                                                                >{isolate.isolate_id}</span
                                                            >
                                                        </div>
                                                    {/each}
                                                {/if}
                                            </td>
                                            <td>
                                                {#if culture.isolates.length === 0}
                                                    <span class="muted"
                                                        >None</span
                                                    >
                                                {:else}
                                                    {#each culture.isolates as isolate}
                                                        {#each flagList(isolate.flags) as flag}
                                                            <span class="flag"
                                                                >{flag}</span
                                                            >
                                                        {/each}
                                                    {/each}
                                                {/if}
                                            </td>
                                            <td>
                                                {#if culture.isolates.length === 0}
                                                    <span class="muted">—</span>
                                                {:else}
                                                    {#each culture.isolates as isolate}
                                                        <div
                                                            class="iso-details"
                                                        >
                                                            {#each Object.entries(isolate.susceptibility) as [agent, result]}
                                                                <span
                                                                    class="susceptibility-pill {result.toLowerCase()}"
                                                                >
                                                                    {agent}: {result}
                                                                </span>
                                                            {/each}
                                                        </div>
                                                    {/each}
                                                {/if}
                                            </td>
                                        </tr>
                                    {/each}
                                </tbody>
                            </table>
                        </div>
                    </section>
                {/if}

                <section class="section-block">
                    <div class="section-header">
                        <h2>Patient history</h2>
                    </div>
                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th>Date</th>
                                    <th>Organism</th>
                                    <th>Specimen</th>
                                    <th>Ward</th>
                                    <th>Flags</th>
                                    <th>Susceptibility</th>
                                </tr>
                            </thead>
                            <tbody>
                                {#if history.length === 0}
                                    <tr>
                                        <td colspan="6"
                                            ><span class="empty-state"
                                                >No previous culture history
                                                available.</span
                                            ></td
                                        >
                                    </tr>
                                {:else}
                                    {#each history as item}
                                        <tr>
                                            <td>{item.sample_date ?? "—"}</td>
                                            <td>{item.organism}</td>
                                            <td>{item.specimen}</td>
                                            <td>{item.ward_code ?? "—"}</td>
                                            <td>
                                                {#if flagList(item.flags).length === 0}
                                                    <span class="muted"
                                                        >None</span
                                                    >
                                                {:else}
                                                    {#each flagList(item.flags) as flag}
                                                        <span class="flag"
                                                            >{flag}</span
                                                        >
                                                    {/each}
                                                {/if}
                                            </td>
                                            <td>
                                                {#each Object.entries(item.susceptibility) as [agent, result]}
                                                    <span
                                                        class="susceptibility-pill {result.toLowerCase()}"
                                                        >{agent}: {result}</span
                                                    >
                                                {/each}
                                            </td>
                                        </tr>
                                    {/each}
                                {/if}
                            </tbody>
                        </table>
                    </div>
                </section>

                <section class="section-block">
                    <div class="section-header">
                        <h2>Empiric recommendations</h2>
                        <p>
                            Decision support only. The recommendation is based
                            on the local ward antibiogram and the patient's
                            expected pathogen/specimen pairing.
                        </p>
                    </div>

                    {#if recommendationGroups.length === 0}
                        <p class="empty-state">
                            No recommendation data available for the current
                            patient findings.
                        </p>
                    {:else}
                        {#each recommendationGroups as group}
                            <div class="recommendation-group">
                                <h3>{group.organism} · {group.specimen}</h3>
                                <div class="table-wrap">
                                    <table>
                                        <thead>
                                            <tr>
                                                <th>Antibiotic</th>
                                                <th>Rate</th>
                                                <th>n</th>
                                                <th>Traffic light</th>
                                                <th>Source</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {#each group.options as option}
                                                <tr>
                                                    <td>{option.antibiotic}</td>
                                                    <td
                                                        >{option.susceptibility_rate ==
                                                        null
                                                            ? "–"
                                                            : `${(option.susceptibility_rate * 100).toFixed(1)}%`}</td
                                                    >
                                                    <td>{option.n}</td>
                                                    <td>
                                                        <span
                                                            class="traffic-pill"
                                                            style={`background:${option.traffic_light === "green" ? "#1f9d61" : option.traffic_light === "yellow" ? "#d29a00" : option.traffic_light === "red" ? "#cf3b3b" : "#5b6470"}`}
                                                        >
                                                            {option.traffic_light}
                                                        </span>
                                                    </td>
                                                    <td
                                                        >{option.source_scope} /
                                                        {option.source_unit} / {option.source_period}</td
                                                    >
                                                </tr>
                                            {/each}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        {/each}
                    {/if}
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
        justify-content: space-between;
        align-items: center;
        gap: 1rem;
        margin-bottom: 1rem;
    }

    .topbar h1 {
        margin: 0;
        font-size: clamp(2rem, 3vw, 2.9rem);
    }

    .topbar p {
        margin: 0.4rem 0 0;
        color: #52657f;
    }

    .nav-link {
        text-decoration: none;
        color: #123b7a;
        background: #eaf1ff;
        border-radius: 999px;
        padding: 0.7rem 1rem;
        font-weight: 600;
    }

    .status-banner {
        margin-bottom: 1.25rem;
        padding: 0.8rem 1rem;
        border-radius: 10px;
        border: 1px solid #dfe7f3;
        font-weight: 600;
    }

    .status-banner.info {
        background: #edf7ff;
        color: #164a87;
    }

    .status-banner.error {
        background: #fff3f3;
        color: #8b2e2e;
    }

    .layout {
        display: grid;
        grid-template-columns: minmax(260px, 340px) minmax(0, 1fr);
        gap: 1.25rem;
        align-items: start;
    }

    .panel {
        background: #ffffff;
        border: 1px solid #dfe7f3;
        border-radius: 16px;
        box-shadow: 0 8px 22px rgba(16, 45, 73, 0.05);
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
    .section-header h2,
    .recommendation-group h3 {
        margin: 0;
    }

    .panel-header input,
    .ward-picker select {
        width: 100%;
        padding: 0.7rem 0.8rem;
        border-radius: 10px;
        border: 1px solid #d8e2f0;
        font: inherit;
        background: white;
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
        padding: 0.9rem 0.9rem;
        border-radius: 12px;
        border: 1px solid #dfe7f3;
        background: #f8fbff;
        cursor: pointer;
        transition: all 0.15s ease;
    }

    .patient-list button:hover,
    .patient-list button.active {
        background: #edf4ff;
        border-color: #7ca7ff;
    }

    .patient-id {
        font-size: 1.02rem;
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
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 0.9rem;
        margin-bottom: 1.2rem;
    }

    .summary-card {
        padding: 0.9rem 1rem;
        border-radius: 12px;
        background: #f9fbff;
        border: 1px solid #dfe7f3;
    }

    .label {
        display: block;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-size: 0.72rem;
        color: #607087;
        margin-bottom: 0.3rem;
    }

    .ward-picker {
        display: flex;
        align-items: center;
        gap: 0.7rem;
        margin-bottom: 1rem;
        flex-wrap: wrap;
    }

    .ward-picker label {
        font-weight: 600;
        color: #3f526d;
    }

    .section-block {
        margin-top: 1.4rem;
    }

    .section-header {
        display: flex;
        align-items: end;
        justify-content: space-between;
        gap: 1rem;
        margin-bottom: 0.75rem;
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
        padding: 0.75rem 0.7rem;
        text-align: left;
        border-bottom: 1px solid #e5ebf4;
        vertical-align: top;
    }

    th {
        text-transform: uppercase;
        font-size: 0.76rem;
        letter-spacing: 0.04em;
        color: #4f647d;
        background: #f7faff;
    }

    .isolate-line,
    .iso-details {
        display: flex;
        flex-wrap: wrap;
        gap: 0.3rem 0.45rem;
        align-items: center;
        margin-bottom: 0.4rem;
    }

    .flag,
    .susceptibility-pill,
    .traffic-pill {
        display: inline-flex;
        align-items: center;
        padding: 0.22rem 0.53rem;
        border-radius: 999px;
        font-size: 0.74rem;
        font-weight: 600;
    }

    .flag {
        background: #edf3ff;
        color: #1f4d99;
    }

    .susceptibility-pill {
        margin: 0 0.3rem 0.35rem 0;
        background: #edf3f8;
        color: #213d5f;
    }

    .susceptibility-pill.s {
        background: #eafaf2;
        color: #166a42;
    }

    .susceptibility-pill.r {
        background: #fff1f1;
        color: #9a2f2f;
    }

    .traffic-pill {
        color: white;
        padding-inline: 0.7rem;
        text-transform: capitalize;
    }

    .recommendation-group {
        margin-top: 0.8rem;
        padding: 1rem;
        border: 1px solid #dfe7f3;
        border-radius: 14px;
        background: #fafcff;
    }

    .recommendation-group h3 {
        margin-bottom: 0.8rem;
    }

    .empty-state {
        display: inline-block;
        padding: 0.8rem 1rem;
        border-radius: 12px;
        border: 1px dashed #cbd6e8;
        color: #5b6f86;
        background: #fafcff;
    }

    .muted {
        color: #6d7f94;
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
