<script lang="ts">
	import type { Snippet } from 'svelte';

	let { children }: { children: Snippet } = $props();
</script>

<div class="recommendations-card">
	{@render children()}
</div>

<style>
	.recommendations-card {
		padding: 1rem;
		overflow-x: auto;
		border-radius: 8px;
		background: var(--color-surface);
		box-shadow: 0 1px 4px rgb(0 0 0 / 0.2);
	}
</style>
