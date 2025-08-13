# Run Congestion — Race Overlap/Throughput Analytics Suite

A production-grade toolkit to **model, detect, and rank on-course congestion** across multi-distance running events (e.g., 10K, Half, Full). The system ingests historical pace distributions and route overlap definitions to surface **acute bottlenecks** and **cumulative interaction intensity** by segment. It ships with a **CLI for local analysis** and a **Vercel-deployed API** suitable for Wix or any web front end.

> TL;DR: Given `your_pace_data.csv`, `overlaps.csv`, start times, and a sampling step, we compute where/when faster runners from one event **intersect** slower runners from another, quantify severity, and rank segments by **Peak Congestion Ratio** or **Intensity**.

---

## What’s New in v1.1.5

- **Automated regression test harness**: `test_runner.sh` runs end-to-end CLI (C1–C7) and API (A1–A8) scenarios and writes timestamped logs to `results/test_runs/`.
- **Expanded documentation**: a comprehensive test plan and `.env` guidance; improved examples and troubleshooting.
- **No API-breaking changes**: Existing CLI/API flags and payloads remain compatible with v1.1.4.

> Note: As of the 1.1.x series, CLI summary CSVs are written to the **`results/`** folder with a time-stamped prefix (e.g., `YYYY-MM-DDTHHMMSS_summary.csv`). fileciteturn6file0

---

## System Architecture (At a Glance)

- **Engine** (`run_congestion/engine.py`): vectorized overlap simulation, two‑phase adaptive stepping, and parallel segment evaluation.
- **CLI** (`python3 -m run_congestion.cli_run_and_export`): local runs with verbose per‑segment details and CSV export.
- **API** (`/api/overlap` on Vercel): JSON-in / rich text-out, with performance headers for quick telemetry, suitable for Wix/JS front ends.
- **Test harness** (`./test_runner.sh`): one-command execution of a full regression plan against local CLI and the live API.

---

## Data Contracts

### 1) Pace CSV (`your_pace_data.csv`)
Required columns:
- `event` — Event label (e.g., `10K`, `Half`, `Full`)
- `runner_id` (or `bib`) — Unique identifier
- `pace` — Pace in **minutes per kilometer** as a decimal (e.g., `3.58` for ~3:35 min/km). If your source uses seconds per km (e.g., `174`), convert to minutes externally (`174/60 ≈ 2.90`).  
- `distance` — Total event distance in km (e.g., `10.0`, `21.1`, `42.2`)

> Optional: `start_time` at runner granularity if you need runner-specific offsets; by default, event-level start times are used.

### 2) Overlaps CSV (`overlaps.csv`)
Schema:
```csv
event,start,end,overlapswith,description
10K,0.00,2.74,Half,"Start to Friel"
10K,5.81,8.10,Half,"Friel to Station/Barker"
Full,16.00,20.52,10K,"Full/10K Friel to Queen Sq. Loop"
Full,23.24,29.03,Half,"Barker/Station to McGloin via Gibson"
Full,29.03,37.00,Half,"Bridge/Mill to/back Tree Farm"
Full,37.00,42.20,Half,"Bridge/Mill to Finish"
```
- `event` is the earlier-starting event.
- `start`, `end` define the inclusive km range (in the **event’s distance scale**).
- `overlapswith` names the later/other event.
- `description` is printed in both verbose and summary outputs.

---

## Installation

> Requires Python 3.10+ (tested), `pip`, and `numpy`/`pandas`.

```bash
git clone https://github.com/thomjeff/run-congestion.git
cd run-congestion

# (Optional) virtual environment
python3 -m venv .venv && source .venv/bin/activate

pip install -r requirements.txt
```

**macOS note:** If you see `permission denied` for scripts, mark them executable:
```bash
chmod +x test_runner.sh
```

---

## Running Locally (CLI)

Primary entrypoint:
```bash
python3 -m run_congestion.cli_run_and_export   data/your_pace_data.csv   data/overlaps.csv   --start-times Full=420 10K=440 Half=460   --time-window 60   --step-km 0.01   --verbose   --rank-by peak_ratio   --export-summary summary.csv
```

### Key flags
- `--start-times`: Event=MinutesFromMidnight (e.g., `Full=420` → 07:00)
- `--time-window`: Overlap tolerance in seconds (default `60`)
- `--step-km` (alias `--step`): Sampling granularity (default typically `0.03` in cloud; locally you can push `0.01`)
- `--rank-by`: `peak_ratio` (default, highlights **acute** bottlenecks) or `intensity` (cumulative interaction count)
- `--segments`: Optional filter list, e.g. `"10K:5.81-8.10" "Full:29.03-37.00"`

### Outputs
- Verbose per-segment block with: first overlap timestamp & km, **Peak Congestion** (headcount), **Peak Ratio**, **Intensity**, and **Distinct Pairs**.
- Ranked **Interaction Intensity Summary** (order controlled by `--rank-by`).
- CSV export to `results/YYYY-MM-DDTHHMMSS_summary.csv` when `--export-summary` is set.

---

## Serverless API (Vercel)

**Endpoint:** `POST https://<your-app>.vercel.app/api/overlap`

**Payload (JSON):**
```json
{
  "paceCsv": "https://raw.githubusercontent.com/thomjeff/run-congestion/main/data/your_pace_data.csv",
  "overlapsCsv": "https://raw.githubusercontent.com/thomjeff/run-congestion/main/data/overlaps.csv",
  "startTimes": {"Full":420, "10K":440, "Half":460},
  "timeWindow": 60,
  "stepKm": 0.03,
  "verbose": true,
  "rankBy": "peak_ratio",
  "segments": ["10K:5.81-8.10", "Full:29.03-37.00"]  // optional
}
```

**Response:** A formatted text report (mirrors CLI verbosity) plus performance headers:
- `x-compute-seconds`: end-to-end compute time
- `x-stepkm`: the **effective** step applied (API may clamp to 0.03 to avoid serverless timeouts)
- `x-request-utc`: server timestamp for traceability

> **Timeout guidance (Vercel Hobby):** With large fields, `stepKm=0.03` is the practical floor to complete within the 300s function limit. Locally you can run `0.01` for finer granularity.

**Quick test (cURL):**
```bash
curl -s -X POST "https://<your-app>.vercel.app/api/overlap"   -H "Content-Type: application/json"   -d '{"paceCsv":"https://raw.githubusercontent.com/thomjeff/run-congestion/main/data/your_pace_data.csv","overlapsCsv":"https://raw.githubusercontent.com/thomjeff/run-congestion/main/data/overlaps.csv","startTimes":{"Full":420,"10K":440,"Half":460},"timeWindow":60,"stepKm":0.03,"verbose":true,"rankBy":"peak_ratio"}'
```

---

## Ranking Metrics

- **Peak Congestion Ratio** = Peak headcount on the segment divided by total runners potentially present (across both events). Optimized for surfacing **acute choke points**.
- **Intensity** = Cumulative overlap events across the segment (higher = more sustained interactions). Optimized for **volume**.

Choose via `--rank-by peak_ratio` (CLI) or `"rankBy":"peak_ratio"` (API).

---

## Performance & Tuning

- **Two-phase adaptive stepping**: coarse scan locates hot zones; fine scan refines only where overlaps exist.
- **Vectorization with NumPy** for arrival-time grids; **pre-filtering** trims impossible pairings.
- **Parallelism**: segments are evaluated concurrently across cores for local runs.

**Controls**
- `stepKm` — smaller is more precise but more expensive; API may clamp to 0.03.
- `timeWindow` — narrower windows reduce matches and runtime.
- `segments` — target only critical segments for faster iterations.

---

## Automated Regression Testing (C1–C7, A1–A8)

We ship a turnkey runner that executes the entire test plan and logs results.

**Setup**
```bash
# If present
cp .env.sample .env

# Otherwise create .env manually
cat > .env <<'EOF'
API_URL=https://<your-app>.vercel.app/api/overlap
PACE_CSV_URL=https://raw.githubusercontent.com/thomjeff/run-congestion/main/data/your_pace_data.csv
OVERLAPS_CSV_URL=https://raw.githubusercontent.com/thomjeff/run-congestion/main/data/overlaps.csv
START_TIMES_JSON={"Full":420,"10K":440,"Half":460}
TIME_WINDOW=60
STEP_KM=0.03
RANK_BY=peak_ratio
VERBOSE=true
EOF

chmod +x test_runner.sh
```

**Run**
```bash
./test_runner.sh list   # discover cases
./test_runner.sh C1     # run a single CLI test
./test_runner.sh A1     # run a single API test
./test_runner.sh all    # run everything
```

**Logs**
- Written to `results/test_runs/<timestamp>_<CASE_ID>.log` (both CLI/API).
- API runs include HTTP headers (`x-compute-seconds`, `x-stepkm`, etc.).

> If you use Finder on macOS: dotfiles are hidden. Toggle visibility with **Cmd+Shift+.** or edit via Terminal (`nano .env`).

---

## Troubleshooting (Tell-It-Like-It-Is)

- **`permission denied: ./script.py`** → `chmod +x script.py` (or run with `python3 script.py`).
- **`No module named pandas`** → `pip install -r requirements.txt` (consider a venv).
- **Curly quotes in JSON** (`stepKm”:0.03`) → replace with straight quotes (`"stepKm": 0.03`).
- **API 500 / FUNCTION_INVOCATION_FAILED** → check `API_URL` (no double `https://`), payload JSON, and that remote CSV URLs are public.
- **No segment matches** → verify `"Event:start-end"` exactly matches an `overlaps.csv` row (whitespace and case are normalized).
- **Vercel timeouts** → raise `stepKm` (≥ 0.03) or limit to `segments` during heavy analyses.

---

## Versioning & Releases

- Tags are immutable; ship forward (e.g., v1.1.4 → v1.1.5 for `test_runner.sh`).  
- Include CHANGELOG entries that map features to tags; avoid amending old releases.

---

## License

Apache-2.0 © 2025

