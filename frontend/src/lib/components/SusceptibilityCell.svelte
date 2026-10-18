<script lang="ts">
	import { hasReportableRate, type AntibioticCell } from '#lib/antibiogram.js';
	import { trafficLightColor, trafficLightTextColor } from '#lib/trafficlight.js';

	let { cell }: { cell?: AntibioticCell } = $props();

	// Missing cell, no rate or not reportable -> unknown ("?").
	const known = $derived(hasReportableRate(cell));
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
	/*
	 * Fixed width so a long badge (e.g. n=2068) wraps under the rate instead of
	 * overlapping it. The auto margins keep the chip centred in a column that is
	 * wider than the chip, under the centred column heading.
	 */
	.chip {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		justify-content: center;
		column-gap: 0.25rem;
		box-sizing: border-box;
		width: 6rem;
		margin-inline: auto;
		padding: 0.25rem 0.5rem;
		border-radius: 4px;
	}

	.chip.unknown {
		border: 1px dashed var(--color-outline);
	}

	/* em so the rate scales with the table font size the print styles set. */
	.rate {
		flex: 1 0 auto;
		font-size: 1.5em;
		text-align: center;
	}

	.badge {
		font-size: 0.75em;
	}
</style>
