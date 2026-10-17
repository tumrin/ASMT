<script lang="ts">
	import type { AntibioticCell } from '#lib/antibiogram.js';
	import { trafficLightColor, trafficLightTextColor } from '#lib/trafficlight.js';

	let { cell }: { cell?: AntibioticCell } = $props();

	// Missing cell, no rate or not reportable -> unknown ("?").
	const known = $derived(
		cell !== undefined && cell.susceptibility_rate !== null && cell.traffic_light !== 'none'
	);
</script>

{#if known && cell}
	<div
		class="chip"
		style:background={trafficLightColor(cell.traffic_light)}
		style:color={trafficLightTextColor(cell.traffic_light)}
	>
		<span class="rate">{Math.round((cell.susceptibility_rate ?? 0) * 100)}</span>
		<span class="badge">n={cell.n}</span>
	</div>
{:else}
	<div class="chip unknown" title={cell ? `n=${cell.n}` : 'No data'}>
		<span class="rate">?</span>
	</div>
{/if}

<style>
	/* Fixed width so a long badge (e.g. n=2068) wraps under the rate instead of overlapping it. */
	.chip {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		justify-content: center;
		column-gap: 0.25rem;
		box-sizing: border-box;
		width: 6rem;
		padding: 0.25rem 0.5rem;
		border-radius: 4px;
	}

	.chip.unknown {
		border: 1px dashed var(--color-outline);
	}

	.rate {
		flex: 1 0 auto;
		font-size: 1.5rem;
		text-align: center;
	}

	.badge {
		font-size: 0.75rem;
	}
</style>
