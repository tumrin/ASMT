<script lang="ts">
	import { onMount } from 'svelte';
	import Icon from '@iconify/svelte';
	import accountIcon from '@iconify-icons/mdi/account';
	import alertIcon from '@iconify-icons/mdi/alert-circle';
	import arrowLeftIcon from '@iconify-icons/mdi/arrow-left';
	import calendarIcon from '@iconify-icons/mdi/calendar-range';
	import flaskIcon from '@iconify-icons/mdi/flask';
	import locationIcon from '@iconify-icons/mdi/map-marker';
	import searchIcon from '@iconify-icons/mdi/magnify';
	import tuneIcon from '@iconify-icons/mdi/tune';
	import { antibioticName } from '#lib/antibiotics.js';
	import {
		findMockPatient,
		mockHistory,
		MOCK_PATIENTS,
		type HistoryEntry,
		type PatientSummary,
		type WardDetail
	} from '#lib/mockPatients.js';
	import { fetchMetadata } from '#lib/metadata.js';
	import { organismName } from '#lib/organisms.js';
	import {
		fetchRecommendations,
		type RecommendationExcluded,
		type RecommendationOption
	} from '#lib/recommendations.js';
	import { specimenName } from '#lib/specimens.js';

	// One recommendations table per distinct organism × specimen finding.
	type RecommendationGroup = {
		organism: string;
		specimen: string;
		options: RecommendationOption[];
		excluded: RecommendationExcluded[];
		dataAsOf: string | null;
	};

	let patientList = $state<PatientSummary[]>([]);
	let patientSummary = $state<PatientSummary | null>(null);
	let selectedPatientId = $state<string>('');
	let selectedWard = $state<string>('');
	let wardDocument = $state<WardDetail | null>(null);
	let history = $state<HistoryEntry[]>([]);
	let recommendationGroups = $state<RecommendationGroup[]>([]);
	let availablePeriods = $state<string[]>(['last4w']);
	let selectedPeriod = $state('last4w');
	let status = $state<string>('Loading patient list...');
	let statusTone = $state<'info' | 'error'>('info');
	let searchTerm = $state<string>('');
	let loading = $state(false);
	let isSelecting = $state(true);
	let selectionVersion = 0;

	const filteredPatients = $derived.by(() => {
		const term = searchTerm.trim().toLowerCase();
		if (!term) return patientList;

		return patientList.filter((patient) => {
			const wardText = patient.wards.join(' ').toLowerCase();
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
					specimen: entry.specimen
				});
			}
		}
		return [...map.values()];
	});

	const age = (birthYear: number) => new Date().getFullYear() - birthYear;

	const periodLabel = (period: string) => {
		if (period === 'last4w') return 'Last 4 weeks';
		const [kind, year] = period.split(':');
		return kind === 'annual' ? `Annual ${year}` : period;
	};

	// Exclusion reasons arrive as snake_case ids (e.g. not_reported_for_specimen).
	function displayWords(value: string): string {
		return value
			.replaceAll('_', ' ')
			.split(/([\s-]+)/)
			.map((part) => (part ? `${part[0].toUpperCase()}${part.slice(1)}` : part))
			.join('');
	}

	const patientNotes = $derived.by(() => {
		const resistantCases = new Map<string, Set<string>>();
		for (const entry of history) {
			for (const [antibiotic, result] of Object.entries(entry.susceptibility)) {
				if (result.toUpperCase() !== 'R') continue;
				const cases = resistantCases.get(antibiotic) ?? new Set<string>();
				cases.add(entry.culture_id);
				resistantCases.set(antibiotic, cases);
			}
		}
		return [...resistantCases.entries()].map(([antibiotic, cases]) => ({
			antibiotic: antibioticName(antibiotic),
			count: cases.size
		}));
	});

	function flagList(flags: { esbl: number; mrsa: number; vre: number; cpe: number }): string[] {
		const list: string[] = [];
		if (flags.esbl) list.push('ESBL');
		if (flags.mrsa) list.push('MRSA');
		if (flags.vre) list.push('VRE');
		if (flags.cpe) list.push('CPE');
		return list;
	}

	async function loadPatientList() {
		loading = true;
		try {
			patientList = MOCK_PATIENTS.map(({ summary }) => summary);
			status = `Loaded ${patientList.length} mock patients.`;
			statusTone = 'info';

			try {
				const metadata = await fetchMetadata();
				availablePeriods = metadata.periods?.length ? metadata.periods : ['last4w'];
			} catch (error) {
				console.error(error);
				availablePeriods = ['last4w'];
			}
		} catch (error) {
			console.error(error);
			status = 'Failed to load patients from the backend.';
			statusTone = 'error';
		} finally {
			loading = false;
		}
	}

	async function loadRecommendationsForFinding(
		wardCode: string,
		organism: string,
		specimen: string,
		period: string
	): Promise<RecommendationGroup> {
		const payload = await fetchRecommendations({
			scope: 'ward',
			unit: wardCode,
			organism,
			specimen,
			period
		});
		return {
			organism,
			specimen,
			options: payload.options ?? [],
			excluded: payload.excluded ?? [],
			dataAsOf: payload.data_as_of
		};
	}

	async function refreshRecommendations() {
		const patientId = selectedPatientId;
		const wardCode = selectedWard;
		const period = selectedPeriod;
		if (!selectedPatientId || !selectedWard || uniqueOrganismSpecimens.length === 0) {
			recommendationGroups = [];
			return;
		}

		const findings = await Promise.all(
			uniqueOrganismSpecimens.map(({ organism, specimen }) =>
				loadRecommendationsForFinding(wardCode, organism, specimen, period)
			)
		);

		if (selectedPatientId !== patientId || selectedWard !== wardCode || selectedPeriod !== period)
			return;
		recommendationGroups = findings.filter((item) => item.options.length > 0);
	}

	async function selectPeriod(period: string) {
		selectedPeriod = period;
		loading = true;
		try {
			await refreshRecommendations();
		} catch (error) {
			console.error(error);
			status = 'Unable to load recommendations for this timeframe.';
			statusTone = 'error';
		} finally {
			loading = false;
		}
	}

	async function selectPatient(patientId: string) {
		const requestVersion = ++selectionVersion;
		selectedPatientId = patientId;
		isSelecting = false;
		searchTerm = '';
		patientSummary = null;
		selectedWard = '';
		wardDocument = null;
		history = [];
		recommendationGroups = [];
		loading = true;
		try {
			const mock = findMockPatient(patientId);
			if (!mock) throw new Error(`Unknown mock patient ${patientId}`);
			const summary = mock.summary;
			if (requestVersion !== selectionVersion) return;
			patientSummary = summary;

			const wardChoices = summary.wards ?? [];
			selectedWard = wardChoices[0] ?? '';
			const ward = mock.ward.ward_code === selectedWard ? mock.ward : null;
			if (requestVersion !== selectionVersion) return;
			wardDocument = ward;
			history = ward ? mockHistory(ward) : [];
			await refreshRecommendations();
			status = `Loaded patient ${patientId}.`;
			statusTone = 'info';
		} catch (error) {
			if (requestVersion !== selectionVersion) return;
			console.error(error);
			status = `Unable to load recommendations for ${patientId}.`;
			statusTone = 'error';
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
			const mock = findMockPatient(patientId);
			const ward = mock?.ward.ward_code === wardCode ? mock.ward : null;
			if (!ward) throw new Error(`Unknown mock ward ${wardCode} for ${patientId}`);
			if (selectedPatientId !== patientId || selectedWard !== wardCode) return;
			wardDocument = ward;
			history = mockHistory(ward);
			await refreshRecommendations();
		} catch (error) {
			if (selectedPatientId !== patientId || selectedWard !== wardCode) return;
			console.error(error);
			status = `Unable to load ward ${wardCode}.`;
			statusTone = 'error';
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
		{#if isSelecting}
			<h1>Select a patient</h1>
		{:else}
			<button class="back-button" type="button" onclick={() => (isSelecting = true)}>
				<Icon icon={arrowLeftIcon} aria-hidden="true" />
				Back to selection
			</button>
		{/if}
	</header>

	{#if statusTone === 'error'}
		<p class="status-banner error" role="alert">{status}</p>
	{/if}

	<div>
		<aside class="patient-list-panel" hidden={!isSelecting}>
			<div class="panel-header">
				<label class="search-field">
					<Icon icon={searchIcon} aria-hidden="true" />
					<input
						bind:value={searchTerm}
						type="search"
						placeholder="Search patients, wards or areas"
						aria-label="Search patient list"
					/>
				</label>
			</div>

			{#if filteredPatients.length === 0}
				<p class="empty-state">No patients match the current search.</p>
			{:else}
				<ul class="patient-list">
					{#each filteredPatients as patient}
						<li>
							<button
								type="button"
								class:active={selectedPatientId === patient.patient_id}
								onclick={() => void selectPatient(patient.patient_id)}
							>
								<div class="patient-id">
									{patient.patient_id}
								</div>
								<div class="patient-meta">
									{patient.sex} · {age(patient.birth_year)} yrs
								</div>
								<div class="patient-meta">
									{patient.wards.join(', ') || 'No ward data'}
								</div>
							</button>
						</li>
					{/each}
				</ul>
			{/if}
		</aside>

		<main class="patient-detail-panel" hidden={isSelecting}>
			{#if patientSummary}
				<section class="section-block scope-section">
					<div class="section-header">
						<h2><Icon icon={tuneIcon} aria-hidden="true" />Scope</h2>
					</div>
					<div class="scope-grid">
						<div class="scope-card">
							<div class="scope-label">
								<Icon icon={locationIcon} aria-hidden="true" />
								Location
							</div>
							<select
								aria-label="Location"
								value={selectedWard}
								onchange={(event) => void selectWard(event.currentTarget.value)}
							>
								{#each patientSummary.wards as wardCode (wardCode)}
									<option value={wardCode}>{wardCode} (Ward)</option>
								{/each}
							</select>
						</div>
						<div class="scope-card">
							<div class="scope-label">
								<Icon icon={calendarIcon} aria-hidden="true" />
								Timeframe
							</div>
							<select
								aria-label="Timeframe"
								value={selectedPeriod}
								onchange={(event) => void selectPeriod(event.currentTarget.value)}
							>
								{#each availablePeriods as period (period)}
									<option value={period}>{periodLabel(period)}</option>
								{/each}
							</select>
						</div>
					</div>
				</section>

				<section class="section-block patient-info-section">
					<div class="section-header">
						<h2><Icon icon={accountIcon} aria-hidden="true" />Patient Info</h2>
					</div>
					<div class="summary-grid">
						<div class="summary-card">
							<span class="label">Age</span>
							<strong>{age(patientSummary.birth_year)}</strong>
						</div>
						<div class="summary-card">
							<span class="label">Sex</span>
							<strong>{patientSummary.sex}</strong>
						</div>
						<div class="summary-card">
							<span class="label">Area</span>
							<strong>{patientSummary.home_area}</strong>
						</div>
					</div>
				</section>

				{#snippet patientCulturesBlock()}
					{#if wardDocument}
						<details class="data-details">
							<summary>
								<Icon icon={flaskIcon} aria-hidden="true" />
								Cultures ({wardDocument.cultures.length})
							</summary>
							<section class="section-block culture-section">
								<div class="section-header">
									<h2>Ward cultures</h2>
									<p>
										{wardDocument.ward_fi ?? wardDocument.ward_en ?? wardDocument.ward_code}
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
																<div class="isolate-line">
																	<strong>{isolate.organism}</strong>
																	<span>{isolate.isolate_id}</span>
																</div>
															{/each}
														{/if}
													</td>
													<td>
														{#if culture.isolates.length === 0}
															<span class="muted">None</span>
														{:else}
															{#each culture.isolates as isolate}
																{#each flagList(isolate.flags) as flag}
																	<span class="flag">{flag}</span>
																{/each}
															{/each}
														{/if}
													</td>
													<td>
														{#if culture.isolates.length === 0}
															<span class="muted">—</span>
														{:else}
															{#each culture.isolates as isolate}
																<div class="iso-details">
																	{#each Object.entries(isolate.susceptibility) as [agent, result]}
																		<span class="susceptibility-pill {result.toLowerCase()}">
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
						</details>
					{/if}
				{/snippet}

				{#snippet patientNotesBlock()}
					<section class="section-block notes-section">
						<div class="section-header">
							<h2><Icon icon={alertIcon} aria-hidden="true" />Notes ({patientNotes.length})</h2>
						</div>
						{#if patientNotes.length === 0}
							<p class="empty-state">No resistance history recorded.</p>
						{:else}
							<div class="notes-list">
								{#each patientNotes as note (note.antibiotic)}
									<div class="note-banner">
										<Icon class="note-icon" icon={alertIcon} aria-hidden="true" />
										<span>
											Patient history of {note.antibiotic} resistance ({note.count} previous {note.count ===
											1
												? 'case'
												: 'cases'})
										</span>
									</div>
								{/each}
							</div>
						{/if}
						<details class="data-details history-details">
							<summary>Patient history ({history.length})</summary>
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
													><span class="empty-state">No previous culture history available.</span
													></td
												>
											</tr>
										{:else}
											{#each history as item}
												<tr>
													<td>{item.sample_date ?? '—'}</td>
													<td>{item.organism}</td>
													<td>{item.specimen}</td>
													<td>{item.ward_code ?? '—'}</td>
													<td>
														{#if flagList(item.flags).length === 0}
															<span class="muted">None</span>
														{:else}
															{#each flagList(item.flags) as flag}
																<span class="flag">{flag}</span>
															{/each}
														{/if}
													</td>
													<td>
														{#each Object.entries(item.susceptibility) as [agent, result]}
															<span class="susceptibility-pill {result.toLowerCase()}"
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
						</details>
					</section>
				{/snippet}

				<section class="section-block recommendations-section">
					<div class="section-header">
						<h2><Icon icon={flaskIcon} aria-hidden="true" />Recommendations</h2>
						<p>
							{#if recommendationGroups[0]?.dataAsOf}(as of {recommendationGroups[0].dataAsOf}){/if}
						</p>
					</div>

					{#if recommendationGroups.length === 0}
						<p class="empty-state">
							No recommendation data available for the current patient findings.
						</p>
					{:else}
						{#each recommendationGroups as group}
							<div class="recommendation-group">
								<h3>{organismName(group.organism)} · {specimenName(group.specimen)}</h3>
								<div class="table-wrap">
									<table>
										<thead>
											<tr>
												<th>Name (code)</th>
												<th>Susceptibility</th>
											</tr>
										</thead>
										<tbody>
											{#each group.options as option}
												<tr>
													<td class="antibiotic-name">
														{antibioticName(option.antibiotic_code)} ({option.antibiotic_code})
													</td>
													<td>
														<div class="rate-cell traffic-{option.traffic_light}">
															<strong
																>{option.susceptibility_rate == null
																	? '?'
																	: Math.round(option.susceptibility_rate * 100)}</strong
															>
															{#if option.susceptibility_rate != null}<span>%</span>{/if}
															<small
																>n={option.n} · {option.source_scope} / {option.source_unit} / {option.source_period}</small
															>
														</div>
													</td>
												</tr>
											{/each}
										</tbody>
									</table>
								</div>
								{#if group.excluded.length > 0}
									<details class="excluded-list">
										<summary>Show excluded ({group.excluded.length})</summary>
										<ul>
											{#each group.excluded as item (`${item.antibiotic_code}-${item.reason}`)}
												<li>
													<span
														>{antibioticName(item.antibiotic_code)} ({item.antibiotic_code})</span
													>
													<small>{displayWords(item.reason)}: {item.detail}</small>
												</li>
											{/each}
										</ul>
									</details>
								{/if}
							</div>
						{/each}
					{/if}
					<p class="decision-support">Decision support only. Not a prescription.</p>
				</section>
				{@render patientNotesBlock()}
				{@render patientCulturesBlock()}
			{:else}
				<p class="empty-state">Choose a patient from the list to inspect their record.</p>
			{/if}
		</main>
	</div>
</div>

<style>
	* {
		box-sizing: border-box;
	}

	.page-shell {
		max-width: 760px;
		margin: 0 auto;
		padding: 0.45rem 0 2rem;
	}

	.topbar {
		display: flex;
		justify-content: flex-start;
		align-items: center;
		gap: 1rem;
		min-height: 1.5rem;
		margin: 0 0 0.55rem;
	}

	.topbar h1 {
		margin: 0;
		font-size: 1.05rem;
	}

	.back-button {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		padding: 0;
		border: 0;
		background: transparent;
		color: #5b3a86;
		font: inherit;
		font-size: 0.8rem;
		cursor: pointer;
	}

	.back-button :global(svg) {
		width: 1rem;
		height: 1rem;
	}

	.status-banner {
		margin-bottom: 1.25rem;
		padding: 0.8rem 1rem;
		border-radius: 10px;
		border: 1px solid #dfe7f3;
		font-weight: 600;
	}

	.status-banner.error {
		background: #fff3f3;
		color: #8b2e2e;
	}

	.patient-list-panel[hidden],
	.patient-detail-panel[hidden] {
		display: none;
	}

	.patient-detail-panel {
		display: flex;
		flex-direction: column;
		padding: 0;
	}

	.panel-header {
		display: flex;
		flex-direction: column;
		gap: 0.65rem;
		margin-bottom: 0.75rem;
	}

	.search-field {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.65rem 0.75rem;
		border: 1px solid #ded8e5;
		border-radius: 7px;
		background: #fff;
		color: #77717e;
	}

	.search-field input,
	.scope-card select {
		width: 100%;
		min-width: 0;
		padding: 0;
		border: 0;
		background: transparent;
		font: inherit;
	}

	.search-field input {
		outline: 0;
	}

	.scope-card select {
		color: #28252d;
		font-size: 0.85rem;
	}

	.search-field :global(svg) {
		flex: 0 0 auto;
		width: 1.1rem;
		height: 1.1rem;
	}

	.patient-list {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		gap: 0.5rem;
	}

	.patient-list button {
		width: 100%;
		text-align: left;
		padding: 0.7rem 0.8rem;
		border: 1px solid #e7e1eb;
		border-radius: 7px;
		background: #fff;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.patient-list button:hover,
	.patient-list button.active {
		border-color: #b59acb;
		background: #f4eef9;
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

	.section-block {
		margin-top: 0;
		margin-bottom: 0.6rem;
	}

	.section-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		margin-bottom: 0.45rem;
	}

	.section-header h2 {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		margin: 0;
		color: #292630;
		font-size: 0.98rem;
		font-weight: 500;
	}

	.section-header h2 :global(svg) {
		width: 1rem;
		height: 1rem;
		color: #35313b;
	}

	.section-header p {
		margin: 0;
		color: #696472;
		font-size: 0.72rem;
		white-space: nowrap;
	}

	.scope-grid {
		display: grid;
		grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
		gap: 0.5rem;
	}

	.scope-card {
		position: relative;
		min-width: 0;
		min-height: 3rem;
		padding: 0.55rem 0.7rem 0.45rem;
		border: 1px solid #eeebf0;
		border-radius: 7px;
		background: #fff;
	}

	.scope-label {
		display: flex;
		align-items: center;
		gap: 0.3rem;
		margin-bottom: 0.2rem;
		color: #625d68;
		font-size: 0.7rem;
	}

	.scope-label :global(svg) {
		width: 0.85rem;
		height: 0.85rem;
		color: #46414b;
	}

	.summary-grid {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 0.5rem;
		margin: 0;
	}

	.summary-card {
		min-width: 0;
		min-height: 2.8rem;
		padding: 0.55rem 0.65rem;
		border: 1px solid #eeebf0;
		border-radius: 7px;
		background: #fff;
	}

	.summary-card strong {
		display: block;
		overflow: hidden;
		font-size: 1.05rem;
		font-weight: 500;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.label {
		display: block;
		margin-bottom: 0.15rem;
		color: #625d68;
		font-size: 0.7rem;
		letter-spacing: 0;
		text-transform: none;
	}

	.data-details {
		margin: 0.2rem 0 1rem;
		border-top: 1px solid #e5dfe9;
	}

	.data-details > summary {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.55rem 0;
		color: #4a4451;
		font-size: 0.82rem;
		cursor: pointer;
		list-style: none;
	}

	.data-details > summary::-webkit-details-marker {
		display: none;
	}

	.data-details > summary::after {
		margin-left: auto;
		content: '⌄';
		color: #776d80;
	}

	.data-details[open] > summary::after {
		content: '⌃';
	}

	.data-details > summary :global(svg) {
		width: 0.95rem;
		height: 0.95rem;
	}

	.culture-section {
		margin: 0 0 0.75rem;
	}

	.notes-section {
		margin-bottom: 0.85rem;
	}

	.notes-section .section-header {
		margin-bottom: 0.3rem;
	}

	.note-banner {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		min-height: 2.45rem;
		padding: 0.45rem 0.65rem;
		border: 1px solid #f1cece;
		border-radius: 7px;
		background: #f9dddd;
		color: #7d3535;
		font-size: 0.72rem;
		line-height: 1.3;
	}

	.note-icon {
		flex: 0 0 auto;
		width: 1rem;
		height: 1rem;
		color: #a73838;
	}

	.history-details {
		margin-top: 0.5rem;
		border: 0;
	}

	.history-details > summary {
		padding: 0.4rem 0;
		font-size: 0.73rem;
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
	.susceptibility-pill {
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

	.muted {
		color: #6d7f94;
	}

	.recommendations-section {
		display: flex;
		flex-direction: column;
	}

	.recommendation-group + .recommendation-group {
		margin-top: 0.7rem;
		padding-top: 0.55rem;
		border-top: 1px solid #e5dfe9;
	}

	.recommendation-group h3 {
		margin: 0 0 0.3rem;
		color: #625d68;
		font-size: 0.72rem;
		font-weight: 500;
	}

	.recommendation-group .table-wrap {
		overflow: visible;
	}

	.recommendation-group table {
		min-width: 0;
		table-layout: fixed;
	}

	.recommendation-group th,
	.recommendation-group td {
		padding: 0.18rem 0.25rem;
		border: 0;
		background: transparent;
	}

	.recommendation-group th {
		color: #655f6b;
		font-size: 0.62rem;
		font-weight: 500;
		text-transform: none;
	}

	.recommendation-group th:first-child,
	.recommendation-group td:first-child {
		width: 43%;
		padding-left: 0;
	}

	.recommendation-group td:last-child {
		width: 57%;
	}

	.antibiotic-name {
		color: #2f2b34;
		font-size: 0.76rem;
		line-height: 1.2;
		overflow-wrap: anywhere;
	}

	.rate-cell {
		display: grid;
		grid-template-columns: auto 1fr;
		align-items: baseline;
		column-gap: 0.12rem;
		min-height: 2.05rem;
		padding: 0.18rem 0.35rem 0.14rem;
		border: 1px solid transparent;
		border-radius: 5px;
		color: #292630;
	}

	.rate-cell strong {
		font-size: 0.92rem;
		font-weight: 500;
		line-height: 1;
	}

	.rate-cell > span {
		font-size: 0.7rem;
	}

	.rate-cell small {
		grid-column: 1 / -1;
		margin-top: 0.08rem;
		color: #4c5b4c;
		font-size: 0.53rem;
		line-height: 1.1;
		overflow-wrap: anywhere;
	}

	.traffic-green {
		border-color: #a9dba8;
		background: #b9efb7;
	}

	.traffic-yellow {
		border-color: #e9c58a;
		background: #ffe0ad;
	}

	.traffic-red {
		border-color: #e5aaaa;
		background: #f5cccc;
	}

	.traffic-none {
		border-color: #d9d4de;
		background: #f6f4f7;
	}

	.decision-support {
		margin: 0.4rem 0 0;
		color: #77717e;
		font-size: 0.65rem;
	}

	.empty-state {
		display: inline-block;
		padding: 0.6rem 0.7rem;
		border: 1px dashed #cbd6e8;
		border-radius: 6px;
		color: #5b6f86;
		background: #fafcff;
		font-size: 0.8rem;
	}

	.excluded-list {
		margin: 0.3rem 0 0 43%;
		color: #655f6b;
		font-size: 0.65rem;
	}

	.excluded-list > summary {
		width: fit-content;
		color: #5b3a86;
		cursor: pointer;
		list-style: none;
	}

	.excluded-list > summary::-webkit-details-marker {
		display: none;
	}

	.excluded-list > summary::before {
		margin-right: 0.3rem;
		content: '⌄';
	}

	.excluded-list[open] > summary::before {
		content: '⌃';
	}

	.excluded-list ul {
		display: grid;
		gap: 0.35rem;
		padding: 0.45rem 0 0.2rem;
		margin: 0;
		list-style: none;
	}

	.excluded-list li {
		display: grid;
		gap: 0.1rem;
		padding-top: 0.25rem;
		border-top: 1px solid #e5dfe9;
	}

	.excluded-list li small {
		color: #77717e;
		font-size: 0.6rem;
	}

	@media (max-width: 920px) {
		.topbar {
			flex-direction: column;
			align-items: flex-start;
		}
	}

	@media (max-width: 420px) {
		.scope-grid {
			grid-template-columns: minmax(0, 1.7fr) minmax(0, 1fr);
		}

		.section-header h2 {
			font-size: 1rem;
		}

		.rate-cell small {
			font-size: 0.5rem;
		}
	}

	@media (min-width: 640px) {
		.page-shell {
			padding-top: 1.25rem;
		}

		.scope-card,
		.summary-card {
			min-height: 4.1rem;
			padding-top: 0.7rem;
		}

		.recommendation-group th:first-child,
		.recommendation-group td:first-child {
			width: 35%;
		}

		.recommendation-group td:last-child {
			width: 65%;
		}

		.rate-cell {
			grid-template-columns: auto 1fr;
			min-height: 2.4rem;
			padding: 0.3rem 0.55rem;
		}

		.rate-cell strong {
			font-size: 1rem;
		}

		.rate-cell small {
			font-size: 0.62rem;
		}
	}
</style>
