# frontend

Web client for the cumulative antibiogram application. It renders the antibiogram,
the empiric recommendations and, as a nice to have, the patient view from the backend
API. The frontend does no rate calculations; every value it shows comes from the
backend (spec.md §4).

## Technology stack

- Svelte 5 (runes mode forced for project files in `vite.config.ts`)
- SvelteKit 3 with `@sveltejs/adapter-auto`
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

The views call the backend API, so start it first (see Development in
`server/README.md`); it serves on `http://127.0.0.1:8000`. There is no dev proxy or
backend base URL setting yet (see Implementation status), so the frontend cannot reach
the API until one is added.

There are no tests, linter or formatter set up yet, so `npm run check` is the only
check to run before you push.

`adapter-auto` only supports some environments; pick a specific adapter once the
deployment target is known (https://svelte.dev/docs/kit/adapters).

## Layout

```
src/
  app.html            HTML shell
  app.d.ts            App namespace types (all empty)
  lib/
    index.ts          `#lib` alias entry (empty)
    assets/favicon.svg
  routes/
    +layout.svelte    sets the favicon, renders children
    +page.svelte      SvelteKit welcome placeholder
static/
  robots.txt
```

`#lib` and `#lib/*` are Node subpath imports declared in `package.json`.

## Views

The sections from here down to Implementation status are the frontend specification
moved from `spec.md`.

### Antibiogram (spec.md §3.2)

- A matrix of organisms (rows) × antibiotics (columns). Each row is one
  organism × specimen type pair, so *E. coli* (urine) and *E. coli* (blood) are
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
  `n`, interval, `traffic_light` and the scope and period the rate came from; show
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

The project is a fresh SvelteKit scaffold; the Views section describes the finished
product. Not implemented yet:

- All views: `routes/+page.svelte` is still the SvelteKit welcome placeholder.
- API client: no fetch code, backend base URL setting or dev proxy in
  `vite.config.ts`.
- PDF export: no PDF library chosen.
- Deployment adapter: `adapter-auto` is still in place.

The backend does not serve `/antibiogram`, `/recommendations` or `/patients` yet (see
Conflicts in `server/README.md`), so the views have no endpoints to call until it does.
