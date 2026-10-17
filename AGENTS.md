# AGENTS.md

This file guides AI coding agents working in this repository.

## Project

Hackathon app: a cumulative antibiogram over the **synthetic** microbiology dataset in `data/`. End users are doctors and nurses.

Read the doc that matches your task before you change anything:

- [`spec.md`](spec.md): product requirements.
- [`user_stories.md`](user_stories.md): user stories, shared definitions and open questions.
- [`data/README.md`](data/README.md): dataset structure, columns and antibiotics (Finnish/English).
- [`server/README.md`](server/README.md): backend usage, development, layout and pipeline specification.
- [`frontend/README.md`](frontend/README.md): frontend.

**Hard constraint:** only the CSVs in `data/` may be used. Never enrich them with external or curated clinical metadata. Every derived field must come from the CSVs arithmetically. Deviations and outliers are reported only. They never remove or rewrite records.
