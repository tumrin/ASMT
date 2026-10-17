<script lang="ts">
	import type { AntibioticCell } from '#lib/antibiogram.js';
	import { antibioticName, type AntibioticCode } from '#lib/antibiotics.js';
	import SusceptibilityCell from './SusceptibilityCell.svelte';

	// One cell per organism column; undefined when that organism has no result.
	let { code, cells }: { code: AntibioticCode; cells: (AntibioticCell | undefined)[] } = $props();
</script>

<tr>
	<th scope="row">{antibioticName(code)} ({code})</th>
	{#each cells as cell, i (i)}
		<td><SusceptibilityCell {cell} /></td>
	{/each}
</tr>

<style>
	th {
		font-weight: normal;
		font-size: 1.25rem;
		text-align: left;
	}

	th,
	td {
		padding: 0.5rem;
		border-top: 1px solid var(--color-outline-variant);
	}
</style>
