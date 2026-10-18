<script lang="ts">
	import { onMount } from 'svelte';
	import { fetchAntibiogram, type AntibiogramResponse } from '#lib/antibiogram.js';
	import { ANTIBIOTIC_NAMES, antibioticName, type AntibioticCode } from '#lib/antibiotics.js';
	import RecommendationsCard from '#lib/components/RecommendationsCard.svelte';
	import RecommendationsTable from '#lib/components/RecommendationsTable.svelte';
	import { fetchMetadata, type Metadata } from '#lib/metadata.js';
	import { ORGANISM_NAMES, organismName } from '#lib/organisms.js';
	import { SPECIMEN_NAMES, specimenName } from '#lib/specimens.js';
	import { wardName } from '#lib/wards.js';

	// Annual periods in the available metadata, newest first (e.g. [2026, 2025, ...]).
	function annualYears(periods: string[]): number[] {
		return periods
			.filter((period) => period.startsWith('annual:'))
			.map((period) => Number(period.slice('annual:'.length)))
			.sort((a, b) => b - a);
	}

	// Empty string means no organism filter.
	let organism = $state('');
	// Empty string means no specimen filter.
	let specimen = $state('');
	// "annual" or "last4w".
	let periodKind = $state('annual');
	let year = $state(0);
	// An empty ward or region means it is not selected. They are mutually exclusive:
	// with neither selected the scope is the whole hospital.
	let wardUnit = $state('');
	let regionUnit = $state('');

	let metadata = $state<Metadata | null>(null);
	let metadataError = $state<string | null>(null);

	// The available scopes and periods come from GET /metadata, never from a hardcoded list.
	const years = $derived(annualYears(metadata?.periods ?? []));
	const scope = $derived(wardUnit ? 'ward' : regionUnit ? 'region' : 'hospital');
	const unit = $derived(wardUnit || regionUnit || '-');
	const period = $derived(periodKind === 'last4w' ? 'last4w' : `annual:${year}`);

	let data = $state<AntibiogramResponse | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(false);

	onMount(() => {
		const controller = new AbortController();
		fetchMetadata(controller.signal)
			.then((response) => {
				metadata = response;
				year = annualYears(response.periods)[0] ?? 0;
			})
			.catch((err: unknown) => {
				if (controller.signal.aborted) return;
				metadataError = err instanceof Error ? err.message : String(err);
			});
		return () => controller.abort();
	});

	// Refetch whenever a filter changes; abort the previous request. The metadata must
	// load first so the period and scope names are valid.
	$effect(() => {
		if (!metadata) return;
		const controller = new AbortController();
		loading = true;
		error = null;
		fetchAntibiogram({ scope, unit, period, organism, specimen }, controller.signal)
			.then((response) => {
				data = response;
				loading = false;
			})
			.catch((err: unknown) => {
				if (controller.signal.aborted) return;
				data = null;
				error = err instanceof Error ? err.message : String(err);
				loading = false;
			});
		return () => controller.abort();
	});

	// Every known antibiotic is a row, whether or not the current organisms report it.
	const antibiotics: AntibioticCode[] = Object.keys(ANTIBIOTIC_NAMES).sort((a, b) =>
		antibioticName(a).localeCompare(antibioticName(b), 'fi')
	);

	function printAntibiogram() {
		window.print();
	}
</script>

<svelte:head>
	<title>Antibiogram</title>
</svelte:head>

<div class="page-heading">
	<h1>Antibiogram</h1>
	<button type="button" onclick={printAntibiogram} disabled={loading || !data}>
		Print / Save PDF
	</button>
</div>

<div class="filters">
	<label class="screen-only">
		Organism
		<select bind:value={organism}>
			<option value="">All organisms</option>
			{#each Object.entries(ORGANISM_NAMES) as [id, name] (id)}
				<option value={id}>{name}</option>
			{/each}
		</select>
	</label>

	<label class="screen-only">
		Specimen
		<select bind:value={specimen}>
			<option value="">All</option>
			{#each Object.entries(SPECIMEN_NAMES) as [id, name] (id)}
				<option value={id}>{name}</option>
			{/each}
		</select>
	</label>

	<label class="screen-only">
		Ward
		<select bind:value={wardUnit} onchange={() => (regionUnit = '')}>
			<option value="">All</option>
			{#each metadata?.scopes.ward ?? [] as { unit } (unit)}
				<option value={unit}>{wardName(unit)}</option>
			{/each}
		</select>
	</label>

	<label class="screen-only">
		Region
		<select bind:value={regionUnit} onchange={() => (wardUnit = '')}>
			<option value="">All</option>
			{#each metadata?.scopes.region ?? [] as { unit, label } (unit)}
				<option value={unit}>{label}</option>
			{/each}
		</select>
	</label>

	<label class="screen-only">
		Period
		<select bind:value={periodKind}>
			<option value="annual">Annual</option>
			<option value="last4w">Last 4 weeks</option>
		</select>
	</label>

	{#if periodKind === 'annual'}
		<label>
			Year
			<select bind:value={year}>
				{#each years as y (y)}
					<option value={y}>{y}</option>
				{/each}
			</select>
		</label>
	{/if}
</div>

{#if metadataError}
	<p>Error: {metadataError}</p>
{:else if loading || !metadata}
	<p>Loading…</p>
{:else if error}
	<p>Error: {error}</p>
{:else if data}
	<p class="print-only">
		Filters: {organism ? organismName(organism) : 'All organisms'} ·
		{specimen ? specimenName(specimen) : 'All specimens'} ·
		{scope === 'hospital' ? 'Hospital' : scope === 'region' ? unit : wardName(unit)} ·
		{data.period}
	</p>
	{#if data.organisms.length === 0}
		<p>No results for these filters.</p>
	{:else}
		<RecommendationsCard>
			<RecommendationsTable organisms={data.organisms} {antibiotics} />
		</RecommendationsCard>
	{/if}
{/if}

<style>
	.filters {
		margin: 1rem 0;
	}
	.page-heading {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
	}

	.page-heading button {
		padding: 0.5rem 0.75rem;
		border: 1px solid #52657f;
		border-radius: 4px;
		background: #fff;
		color: #122033;
		font: inherit;
		font-weight: 600;
		cursor: pointer;
	}

	.page-heading button:disabled {
		cursor: not-allowed;
		opacity: 0.55;
	}

	.print-only {
		display: none;
	}

	@media print {
		@page {
			size: landscape;
			margin: 10mm;
		}

		:global(body) {
			color: #000;
			font-size: 9pt;
		}

		:global(.app-header),
		.screen-only,
		.page-heading button {
			display: none !important;
		}

		.page-heading {
			margin-bottom: 0.5rem;
		}

		h1 {
			margin: 0;
			font-size: 18pt;
		}

		.print-only {
			display: block;
		}

		:global(table) {
			font-size: 7pt;
			break-inside: auto;
		}

		:global(thead) {
			display: table-header-group;
		}

		:global(tr) {
			break-inside: avoid;
		}

		:global(th),
		:global(td) {
			padding: 2px;
			print-color-adjust: exact;
		}
	}
</style>
