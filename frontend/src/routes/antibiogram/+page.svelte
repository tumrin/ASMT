<script lang="ts">
	import {
		fetchAntibiogram,
		type AntibioticCell,
		type AntibiogramResponse
	} from '#lib/antibiogram.js';
	import { ANTIBIOTIC_NAMES, antibioticName, type AntibioticCode } from '#lib/antibiotics.js';
	import { ORGANISM_NAMES, organismName } from '#lib/organisms.js';
	import { SPECIMEN_NAMES, specimenName } from '#lib/specimens.js';
	import { trafficLightColor } from '#lib/trafficlight.js';
	import { WARD_NAMES } from '#lib/wards.js';

	// Empty string means no organism filter.
	let organism = $state('');
	// Empty string means no specimen filter.
	let specimen = $state('');
	// Empty string means annual: the backend defaults to the latest year.
	let period = $state('');
	// "-" means the whole hospital; a ward code switches to ward scope.
	let unit = $state('-');

	let data = $state<AntibiogramResponse | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(false);

	// Refetch whenever a filter changes; abort the previous request.
	$effect(() => {
		const controller = new AbortController();
		loading = true;
		error = null;
		fetchAntibiogram({ unit, period, organism, specimen }, controller.signal)
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

	// Every known antibiotic is a column, whether or not the current rows report it.
	const columns: AntibioticCode[] = Object.keys(ANTIBIOTIC_NAMES).sort((a, b) =>
		antibioticName(a).localeCompare(antibioticName(b), 'fi')
	);

	function cellFor(cells: AntibioticCell[], code: string): AntibioticCell | undefined {
		return cells.find((cell) => cell.antibiotic_code === code);
	}
</script>

<svelte:head>
	<title>Antibiogram</title>
</svelte:head>

<h1>Antibiogram</h1>

<label>
	Organism
	<select bind:value={organism}>
		<option value="">All organisms</option>
		{#each Object.entries(ORGANISM_NAMES) as [id, name] (id)}
			<option value={id}>{name}</option>
		{/each}
	</select>
</label>

<label>
	Specimen
	<select bind:value={specimen}>
		<option value="">All</option>
		{#each Object.entries(SPECIMEN_NAMES) as [id, name] (id)}
			<option value={id}>{name}</option>
		{/each}
	</select>
</label>

<label>
	Ward
	<select bind:value={unit}>
		<option value="-">All</option>
		{#each Object.entries(WARD_NAMES) as [code, name] (code)}
			<option value={code}>{name}</option>
		{/each}
	</select>
</label>

<label>
	Period
	<select bind:value={period}>
		<option value="">Annual</option>
		<option value="last4w">Last 4 weeks</option>
	</select>
</label>

{#if loading}
	<p>Loading…</p>
{:else if error}
	<p>Error: {error}</p>
{:else if data}
	<p>Period: {data.period} · Data as of {data.data_as_of ?? 'unknown'}</p>
	{#if data.organisms.length === 0}
		<p>No results for these filters.</p>
	{:else}
		<table border="1">
			<thead>
				<tr>
					<th>Organism</th>
					<th>Specimen</th>
					{#each columns as code (code)}
						<th title={code}>{antibioticName(code)}</th>
					{/each}
				</tr>
			</thead>
			<tbody>
				{#each data.organisms as row (`${row.organism}|${row.specimen}`)}
					<tr>
						<td>{organismName(row.organism)}</td>
						<td>{specimenName(row.specimen)}</td>
						{#each columns as code (code)}
							{@const cell = cellFor(row.antibiotics, code)}
							<td style:background={cell ? trafficLightColor(cell.traffic_light) : undefined}>
								{#if cell}
									{cell.susceptibility_rate === null
										? ''
										: `${Math.round(cell.susceptibility_rate * 100)}% `}(n={cell.n})
								{/if}
							</td>
						{/each}
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
{/if}
