<script lang="ts">
	import Card from '#lib/components/Card.svelte';
	import Subheading from '#lib/components/Subheading.svelte';
</script>

<h1>Welcome to SvelteKit</h1>
<p>Visit <a href="https://svelte.dev/docs/kit">svelte.dev/docs/kit</a> to read the documentation</p>

<Subheading size="medium">Patient info</Subheading>

<Card>Age 52</Card>
<Card elevated>recommendation table</Card>

<style>
	:global(body) {
		background-color: #ccc;
	}
</style>
