<script lang="ts">
	import { hasReportableRate, type AntibiogramRow } from '#lib/antibiogram.js';
	import type { AntibioticCode } from '#lib/antibiotics.js';
	import { organismName } from '#lib/organisms.js';
	import { specimenName } from '#lib/specimens.js';
	import AntibioticRow from './AntibioticRow.svelte';

	// Each organism/specimen row of the antibiogram becomes a column here.
	let {
		organisms,
		antibiotics,
		hideEmpty = false
	}: { organisms: AntibiogramRow[]; antibiotics: AntibioticCode[]; hideEmpty?: boolean } = $props();

	// A column is empty when none of its cells has a reportable rate.
	const columns = $derived(
		hideEmpty ? organisms.filter((row) => row.antibiotics.some(hasReportableRate)) : organisms
	);
</script>

{#if columns.length === 0}
	<p>No reportable results for these filters.</p>
{:else}
	<table>
		<thead>
			<tr>
				<th scope="col">Name (code)</th>
				{#each columns as row (`${row.organism}|${row.specimen}`)}
					<th scope="col">{organismName(row.organism)} ({specimenName(row.specimen)})</th>
				{/each}
			</tr>
		</thead>
		<tbody>
			{#each antibiotics as code (code)}
				<AntibioticRow
					{code}
					cells={columns.map((row) => row.antibiotics.find((c) => c.antibiotic_code === code))}
				/>
			{/each}
		</tbody>
	</table>
{/if}

<style>
	table {
		width: 100%;
		border-collapse: collapse;
	}

	thead th {
		padding: 0.5rem;
		font-weight: normal;
		font-size: 0.875rem;
		text-align: center;
	}

	thead th:first-child {
		text-align: left;
	}

	/* Page-level print rules cannot outrank these scoped ones, so the tighter
	   print padding has to be declared here. */
	@media print {
		thead th {
			padding: 2px;
		}
	}
</style>
