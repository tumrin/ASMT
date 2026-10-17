<script lang="ts">
	import type { Snippet } from 'svelte';

	type Props = {
		size: 'medium' | 'large';
		children: Snippet;
		style?: string;
	};

	let { size, children, style }: Props = $props();
</script>

{#if size === 'medium'}
	<h2 {style}>{@render children()}</h2>
{:else if size === 'large'}
	<h1 {style}>{@render children()}</h1>
{/if}

<style>
	* {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	h1 {
		font-size: 32px;
	}

	h2 {
		font-size: 24px;
	}
</style>
