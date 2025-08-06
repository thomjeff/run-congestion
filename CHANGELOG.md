# Changelog

## [v1.0.0] – 2025-08-06

### Added
- **`detect_overlap.py`**: Core engine with fully vectorized overlap‐detection, delivering scale-resilient performance across large field sizes.  
- **Enhanced CLI**:  
  - `--rank-by` flag to toggle ranking by cumulative **Intensity** or **Peak Ratio** (acute bottlenecks).  
  - `--export-summary` to emit a timestamp-prefixed CSV with embedded metadata (`start_times`, `time_window`, `step`, `generated_at`).  
- **Metrics & Reporting**: Outputs per-segment  
  - **Intensity**, **Intensity/km**, **Peak Congestion**, **Peak Ratio**, **DistinctPairs**  
  - First-overlap context (time, km, runner IDs) and per-segment runtime.  
- **Documentation**:  
  - Comprehensive **README.md** covering overview, definitions, usage, prerequisites, troubleshooting, and dashboard ingestion.  
  - **CHANGELOG.md** established for release tracking.  
- **Excel Artifacts**:  
  - `summary_template.xlsx` (import template + formula guidance)  
  - `summary_dashboard.xlsx` (prebuilt dashboard with bar and scatter charts)

### Changed
- **Removed** JSONL export (`--export-json`) to simplify downstream ingestion (CSV only).

### Next Steps
- Evaluate acute bottlenecks via `--rank-by peak_ratio`.  
- Leverage provided templates for rapid reporting and executive insight.  
