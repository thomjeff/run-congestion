# Density Engine Drop-in (Non-Breaking)

This bundle provides a **backward-compatible** `run_congestion/density.py` plus the Vercel API shim and a CLI wire-up.

## What’s included
- `run_congestion/density.py` — stable `run_density(config)` API, plus `Segment`, `compute_density_steps`, `rollup_segment`, `render_cli_block` (no breaking changes).
- `api/density.py` — FastAPI app exporting `app` with `GET /api/density` and `POST /api/density` (via Vercel’s file-based routing).
- `run_congestion/engine.py` — CLI with `density` subcommand.

## Contract
Your API calls and CLI both route into `run_congestion.density.run_density(config)`.

**Required config keys:**
- `paceCsv` (str URL/path)
- `startTimes` (dict of minutes by event)
- `segments` (array of string specs or objects)

**Optional:**
- `stepKm` (float, default 0.03)
- `timeWindow` (int seconds, default 60)

## Smoke tests

**API (replace with your base):**
```bash
curl -s "https://<base>/api/density" | jq
curl -s -X POST "https://<base>/api/density" -H "Content-Type: application/json" -H "Accept: application/json" -d '{
  "paceCsv":"https://raw.githubusercontent.com/thomjeff/run-congestion/main/data/your_pace_data.csv",
  "startTimes":{"Full":420,"10K":440,"Half":460},
  "segments":[{"eventA":"10K","eventB":"Half","from":0.00,"to":2.74,"width":3.0,"direction":"uni"}],
  "stepKm":0.03,"timeWindow":60
}' | jq
```

**CLI:**
```bash
python -m run_congestion.engine density \
  --pace data/your_pace_data.csv \
  --start-times "Full=420,10K=440,Half=460" \
  --segments "10K,Half,0.00,2.74,3.0,uni; 10K,,2.74,5.80,1.5,bi; 10K,Half,5.81,8.10,3.0,uni"
```
