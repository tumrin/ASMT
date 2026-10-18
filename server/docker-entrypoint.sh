#!/bin/sh
set -eu

# The CSVs are mounted read-only; the artifact is regenerated on every start
# so the API always serves the current data.
/app/.venv/bin/resistance-analysis --out /output
exec /app/.venv/bin/resistance-api --host 0.0.0.0 --port 8000 --dataset /output/dataset.json
