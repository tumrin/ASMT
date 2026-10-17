<script lang="ts">
	import type { AntibiogramRow } from '#lib/antibiogram.js';
	import type { AntibioticCode } from '#lib/antibiotics.js';
	import { organismName } from '#lib/organisms.js';
	import { specimenName } from '#lib/specimens.js';
	import AntibioticRow from './AntibioticRow.svelte';

	// Each organism/specimen row of the antibiogram becomes a column here.
	let { organisms, antibiotics }: { organisms: AntibiogramRow[]; antibiotics: AntibioticCode[] } =
		$props();
</script>

<table>
	<thead>
		<tr>
			<th scope="col">Name (code)</th>
			{#each organisms as row (`${row.organism}|${row.specimen}`)}
				<th scope="col">{organismName(row.organism)} ({specimenName(row.specimen)})</th>
			{/each}
		</tr>
	</thead>
	<tbody>
		{#each antibiotics as code (code)}
			<AntibioticRow
				{code}
				cells={organisms.map((row) => row.antibiotics.find((c) => c.antibiotic_code === code))}
			/>
		{/each}
	</tbody>
</table>

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
</style>
