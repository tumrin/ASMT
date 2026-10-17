<script lang="ts">
</script>

<svelte:head>
    <title>Antibiogram app</title>
</svelte:head>

<div class="shell">
    <main class="card">
        <p class="eyebrow">Cumulative antibiogram</p>
        <h1>Clinical overview</h1>
        <p class="lead">
            This frontend is set up for the antibiogram and patient workflows
            described in the product requirements.
        </p>

        <nav class="nav">
            <a href="/patients">Open patient view</a>
        </nav>
    </main>
</div>

<style>
    :global(body) {
        margin: 0;
        font-family: Inter, "Segoe UI", sans-serif;
        background: linear-gradient(180deg, #eef4ff 0%, #f7fafe 100%);
        color: #16314d;
    }

    * {
        box-sizing: border-box;
    }

    .shell {
        display: grid;
        place-items: center;
        min-height: 100vh;
        padding: 2rem;
    }

    .card {
        max-width: 560px;
        width: 100%;
        padding: 2.2rem;
        border-radius: 20px;
        background: white;
        border: 1px solid #dfe7f3;
        box-shadow: 0 18px 34px rgba(14, 42, 66, 0.08);
    }

    .eyebrow {
        margin: 0 0 0.75rem;
        font-size: 0.76rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #597aa9;
    }

    h1 {
        margin: 0;
        font-size: clamp(2rem, 4vw, 3rem);
    }

    .lead {
        margin: 1rem 0 1.5rem;
        line-height: 1.6;
        color: #49607c;
    }

    .nav {
        display: flex;
        gap: 0.75rem;
        flex-wrap: wrap;
    }

    .nav a {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 0.85rem 1.1rem;
        border-radius: 999px;
        background: #123b7a;
        color: white;
        text-decoration: none;
        font-weight: 600;
    }
</style>
