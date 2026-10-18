<main>
	<h1>ASMT</h1>
	<p class="subheading">Antimicrobial Susceptibility Monitoring Tool</p>

	<div class="buttons">
		<a href="/patients">
			<img src="/qrscan.svg" alt="" />

			<h2>Scan patient tag</h2>
			<p>Patient-specific recommendations</p>
		</a>

		<a href="/patients">
			<img src="/dropdown.svg" alt="" />

			<h2>Select details</h2>
			<p>Patient-specific recommendations</p>
		</a>

		<a href="/antibiogram" class="wide">
			<img src="/table.svg" alt="" />

			<h2>Antibiogram table</h2>
			<p>All antibiogram data in this hospital</p>
		</a>
	</div>
</main>

<style>
	* {
		margin: 0;
		padding: 0;
		box-sizing: border-box;
	}

	.buttons {
		margin-top: 64px;
		display: grid;
		gap: 16px;
		grid-template-columns: 1fr 1fr;

		@media (width < 700px) {
			display: flex;
			flex-direction: column;
		}
	}

	h1 {
		font-size: 57px;
		font-weight: normal;
		color: var(--color-primary);
	}

	.subheading {
		color: #49454f;
	}

	main {
		display: flex;
		width: 100%;
		flex-direction: column;
		padding-top: 64px;
	}

	a {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		text-align: center;
		padding: 32px;
		background-color: #eaddff;
		color: #4f378a;
		border-radius: 12px;
		text-decoration: none;

		&.wide {
			grid-column: span 2;
		}

		img {
			margin-bottom: 16px;
		}
	}
</style>
