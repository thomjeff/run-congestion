# Changelog

## v1.1.4 - 2025-08-13
### Serverless Caching (Option A)

The `/api/overlap` endpoint now implements a cache-first strategy:

- **L1 in-memory cache:** per-instance, fast warm hits.
- **Optional L2 Vercel Blob:** set `BLOB_READ_WRITE_URL` to enable cross-instance caching.
- Cache key includes file content hashes and all relevant parameters (startTimes, timeWindow, stepKm, rankBy).

**Response headers**
- `X-Overlap-Cache: L1 | L2 | MISS`
- `X-Compute-Ms: <milliseconds>`
- `X-StepKm: <value>`

Enable L2 by adding `BLOB_READ_WRITE_URL` in your Vercel Project Settings → Environment Variables.

### Fixes
- **`overlap.py`**: several patches to address incompatibility issues between CLI and JSON/POST usage. 
- Segments normalization: trims & lowercases CSV events and your requested segment events before comparing, so 10K/10k/10K all match.
- No positionals: Calls run_congestion.bridge.analyze_overlaps with keyword args only.
- No DataFrame gotchas: If you request segments, it writes the filtered rows to a temp CSV and passes that path to the engine (which expects a path/URL).
- Plain‑text output: Returns the same human‑readable block you like from the CLI, not JSON. (Error responses are JSON with an “error” key for debugging.)
- Debug headers: X-Events-Seen, X-Request-UTC, X-StepKm so you can verify what the function read at runtime.

## v1.1.3 - 2025-08-12
### Changed
- License from Apache to MIT.

## v1.1.2 - 2025-08-12
### Added
- Summary CSV outputs are now written to a dedicated `results/` folder instead of the `examples/` directory.
- Maintains the existing date-time stamp (YYYY-MM-DDTHHMMSS) prefix for output files.
- Improved file organization for better separation of example data and generated run outputs.

## [1.1.1] - 2025-08-12
## Fixed
- Breaking errors by GPT4o.

## [1.1.0] - 2025-08-06
### Added
- Benchmark timing output: prints total computation time after analysis.
- Pre-filter optimization to eliminate non-overlapping runners before step scanning.
- NumPy broadcasting for vectorized arrival-time matrix computation, replacing Python loops.
- True multi-core parallelism via `ProcessPoolExecutor` in `engine.py`.
- Two-phase adaptive stepping (coarse + refined) to minimize detailed scanning steps.
- `--rank-by` CLI flag to choose summary ranking by `peak_ratio` (default) or `intensity`.
- Timestamped CSV export via `--export-summary <path>`, stored in `examples/` by default.

### Changed
- Refactored `detect_overlap.py` to include timing, ranking, and export functionality.
- Updated `engine.py` with performance optimizations while preserving existing CLI output.
- README updated with new usage instructions and examples.

### Fixed
- Removed unused JSONL export option.
- Clarified file permission instructions (`chmod +x detect_overlap.py`).
