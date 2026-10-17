<script lang="ts">
	import { ORGANISM_NAMES } from '#lib/organisms.js';
	import { SPECIMEN_NAMES } from '#lib/specimens.js';
	import { WARD_NAMES } from '#lib/wards.js';

	// Empty string means no organism filter.
	let organism = $state('');
	// Empty string means no specimen filter.
	let specimen = $state('');
	// Empty string means annual: the backend defaults to the latest year.
	let period = $state('');
	// "-" means the whole hospital; a ward code switches to ward scope.
	let unit = $state('-');
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
