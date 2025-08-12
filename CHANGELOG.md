# Changelog

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
