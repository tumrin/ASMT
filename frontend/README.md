# frontend

Web client for the cumulative antibiogram application. It renders the antibiogram,
the empiric recommendations and, as a nice to have, the patient view from the backend
API. The frontend does no rate calculations; every value it shows comes from the
backend (spec.md §4).

## Technology stack

- Svelte 5 (runes mode forced for project files in `vite.config.ts`)
- SvelteKit 3 with `@sveltejs/adapter-node`
- Vite 8
- TypeScript 6 (`strict`)
- Tooling
  - `svelte-check` for type checking
  - npm for package management (`engine-strict=true` in `.npmrc`)

The project was scaffolded with:

```sh
npx sv@1.1.1 create --template minimal --types ts --install npm frontend
```

## Usage

Run all commands from the `frontend/` directory:

```sh
npm install           # once, and after dependency changes
npm run dev           # http://localhost:5173 with hot reload; add `-- --open` for a browser tab
npm run check:watch   # type check on every change
npm run check         # type check once; run before you push
npm run build         # production build
npm run preview       # serve the production build
```

### Icons

Use Iconify's Svelte component with individual MDI icon imports. This bundles only
the icons used and does not fetch icon data at runtime:

```svelte
<script lang="ts">
  import Icon from '@iconify/svelte';
  import home from '@iconify-icons/mdi/home';
</script>

<Icon icon={home} />
```

The views call the backend API, so start it first (see Development in
`server/README.md`); it serves on `http://127.0.0.1:8000`. The frontend fetches
`/api/*`, and the Vite server (`npm run dev` and `npm run preview`) proxies those
requests to the backend with the `/api` prefix stripped.

### Environment files

The proxy target defaults to `http://127.0.0.1:8000`, so `npm run dev` and
`npm run preview` work without any env file. To point at another backend, copy
`.env.example` to the file for the mode you run and edit it:

```sh
cp .env.example .env.development   # npm run dev
cp .env.example .env.production    # npm run preview
```

| Variable  | Required | Default                 | Description                                   |
| --------- | -------- | ----------------------- | --------------------------------------------- |
| `API_URL` | no       | `http://127.0.0.1:8000` | Backend base URL that `/api/*` is proxied to. |

`API_URL` never reaches browser code. `vite.config.ts` reads it (via `loadEnv`) for
the dev and preview proxies; `src/env.ts` reads it from the process environment when
the built server starts, for the production proxy in `src/hooks.server.ts` (it
defaults to `http://127.0.0.1:8000` when unset, matching `vite.config.ts`). `.env.example` is committed; every
other `.env*` file is gitignored. The built server does not load `.env` files, so
in production set `API_URL` in the server's environment (see `docker-compose.yml`).

There are no tests, linter or formatter set up yet, so `npm run check` is the only
check to run before you push.

## Deployment

`npm run build` produces a standalone Node server with
[`@sveltejs/adapter-node`](https://svelte.dev/docs/kit/adapter-node); run it with
`node build`. It serves on `HOST:PORT` (defaults `0.0.0.0:3000`), reads `API_URL`
from the process environment as described above, and `src/hooks.server.ts` forwards
`/api/*` to it with the prefix stripped. `Dockerfile` builds this, and
`docker-compose.yml` at the repository root runs the whole stack: the API is
internal to the compose network, the frontend is published on host port 8080. Set
`ORIGIN` when a reverse proxy fronts the frontend (needed for form actions and
absolute URLs).

## Layout

```
src/
  app.html            HTML shell
  app.d.ts            App namespace types (all empty)
  env.ts              `API_URL` definition (`defineEnvVars`)
  hooks.server.ts     production `/api/*` proxy to `API_URL`
  lib/
    index.ts          `#lib` alias entry (empty)
    assets/favicon.svg
  routes/
    +layout.svelte    sets the favicon, renders children
    +page.svelte      root page metadata; +page.server.ts redirects to /antibiogram
static/
  robots.txt
```

`#lib` and `#lib/*` are Node subpath imports declared in `package.json`.

## Views

The sections from here down to Implementation status are the frontend specification
moved from `spec.md`.

### Antibiogram (spec.md §3.2)

- A matrix of organisms (rows) × antibiotics (columns). Each row is one
  organism × specimen type pair, so _E. coli_ (urine) and _E. coli_ (blood) are
  separate rows.
- Controls for scope (`hospital`, `ward` for inpatient units, `region` for outpatient
  `home_area`), period (`annual:<year>`, `last4w`) and an optional organism filter.
  The available scopes and periods come from `GET /metadata`.
- All filtering is done by the backend: every control change is a new
  `GET /antibiogram?scope=&unit=&period=&organism=&specimen=` request.
- Each cell shows `susceptibility_rate` and `n`, coloured by the backend's
  `traffic_light` (`green`, `yellow`, `red`, `none`). The frontend does not apply the
  cutoffs itself. Cells with `n < 30` have a null rate and `traffic_light = none`;
  show their `n` without a rate.

### Empiric recommendations (spec.md §3.3, §6.4)

- Input: scope and unit, organism and specimen.
- `POST /recommendations` returns `options` ranked by susceptibility rate, each with
  `n`, `traffic_light` and the scope and period the rate came from; show
  the source scope and period next to each rate, since fallback can make it differ
  from the requested one.
- Show `excluded` agents with their reason, plus `data_as_of` and `limitations`.

### Patient view — nice to have (spec.md §3.4)

- Patient list from `GET /patients`; selecting one opens the individual view.
- Individual view: basic patient information (`GET /patients/{patient_id}`), history
  (`GET /patients/{patient_id}/history`) and the empiric recommendation for each
  finding. History is shown only and does not change the recommendation.

### PDF export (spec.md §3.5)

The antibiogram views and the patient view, including their tables, can be exported
as PDF. This is done entirely in the frontend, with no backend endpoint.

### Users

Doctors and nurses (spec.md §2). There is no authentication or pagination
(spec.md §8).

## Implementation status

The Views section describes the finished product. Implemented so far: a basic
antibiogram page at `/antibiogram` with organism, specimen, ward and region filters
(the ward and region options come from `GET /metadata`; the two scopes are mutually
exclusive) and period filters. Display names for organisms, specimens and wards are

- API client: only `GET /antibiogram` (`src/lib/antibiogram.ts`) is implemented.
- PDF export: the antibiogram uses the browser's print dialog, including the active
  filters; patient-view export is not implemented.
