<script lang="ts">
	import type { Snippet } from 'svelte';

	type Props = {
		children: Snippet;
		elevated?: boolean;
		style?: string;
	};

	let { children, elevated, style }: Props = $props();
</script>

<div class:elevated {style}>
	{@render children()}
</div>

<style>
	div {
		display: flex;
		flex-direction: column;
		gap: 4px;
		background-color: #fff;
		border-radius: 12px;
		padding: 24px 16px;

		&.elevated {
			box-shadow:
				0px 1px 3px rgba(0, 0, 0, 0.3),
				0px 4px 8px rgba(0, 0, 0, 0.15);
		}
	}
</style>
