<script lang="ts">
	import { page } from "$app/state";
	import favicon from "#lib/assets/favicon.svg";
	import type { LayoutProps } from "./$types";

	let { children }: LayoutProps = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<header class="app-header">
	<a class="brand" href="/antibiogram">Cumulative antibiogram</a>
	<nav aria-label="Main navigation">
		<a
			href="/antibiogram"
			aria-current={page.url.pathname.startsWith("/antibiogram")
				? "page"
				: undefined}
		>
			Antibiogram
		</a>
		<a
			href="/patients"
			aria-current={page.url.pathname.startsWith("/patients")
				? "page"
				: undefined}
		>
			Patients
		</a>
	</nav>
</header>

<main class="container">
	{@render children()}
</main>

<style>
	.container {
		margin: 0 3rem;
	}
	.app-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		min-height: 3.5rem;
		padding: 0 1.5rem;
		border-bottom: 1px solid #dfe7f3;
		background: #fff;
		color: #122033;
	}

	.brand {
		color: inherit;
		font-weight: 700;
		text-decoration: none;
	}

	nav {
		display: flex;
		align-self: stretch;
		gap: 0.25rem;
	}

	nav a {
		display: inline-flex;
		align-items: center;
		padding: 0 0.85rem;
		border-bottom: 2px solid transparent;
		color: #52657f;
		font-weight: 600;
		text-decoration: none;
	}

	nav a:hover,
	nav a[aria-current="page"] {
		border-bottom-color: #123b7a;
		color: #123b7a;
	}

	.brand:focus-visible,
	nav a:focus-visible {
		outline: 2px solid #123b7a;
		outline-offset: -2px;
	}

	@media (max-width: 480px) {
		.app-header {
			gap: 0.5rem;
			padding: 0 0.75rem;
		}

		.brand {
			font-size: 0.875rem;
		}

		nav a {
			padding: 0 0.55rem;
		}
	}
</style>
