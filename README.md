# Race Congestion Detection Suite

A modular Python toolkit to analyze and mitigate on-course congestion among running events.  

This release (v1.1.0) introduces major performance optimizations and new CLI features while maintaining backward-compatible output formats.

## Features (v1.1.0)

- **Benchmark timing**: Total computation time printed after analysis.
- **Pre-filter optimization**: Quickly exclude runners with non-overlapping arrival windows.
- **NumPy broadcasting**: Vectorized arrival-time matrix computation for speed.
- **Multi-core processing**: `ProcessPoolExecutor` parallelizes segments across CPU cores.
- **Adaptive two-phase stepping**: Coarse scan to locate overlap zones, refined scan only where needed.
- **CLI enhancements**:
  - `--rank-by` flag (`peak_ratio` or `intensity`)
  - `--export-summary <file>` writes a timestamped CSV (e.g. `2025-08-06T204130_summary.csv`)
  - `--time-window` and `--step` remain to control tolerance and resolution.

## Installation

```bash
git clone https://github.com/<username>/run-congestion.git
cd run-congestion
chmod +x src/detect_overlap.py
pip install -r requirements.txt
```

> **Note:** Requires Python 3.8+ and pandas, numpy.

## Overlaps CSV Format

Your `overlaps.csv` should have columns:

```csv
event,start,end,overlapsWith,description
10K,0.00,2.74,Half,"Start to Friel"
10K,5.81,8.10,Half,"Friel to Station/Barker"
Full,16.00,20.52,10K,"Full/10K Friel to Queen Sq. Loop"
...
```

- **event**: The earlier-starting event.
- **start**, **end**: kilometer range for overlap.
- **overlapsWith**: the later event.
- **description**: human-readable segment name.

## Usage

```bash
./src/detect_overlap.py data/your_pace_data.csv data/overlaps.csv   --start-times Full=420 10K=440 Half=460   --time-window 60   --step 0.01   --rank-by peak_ratio   --verbose   --export-summary summary.csv
```

- The script will print per-segment details and a ranked interaction summary.
- Summary CSV is written to `examples/<timestamp>_summary.csv`.

## Performance Tips

- Default `step=0.01` (10 m) and `time-window=60` s balance detail and speed.
- For extremely long segments, consider increasing `coarse_factor` in code.
- To further reduce runtime, integrate Numba JIT or full-array 3D mask scanning.

## Examples

See [examples/summary.csv](examples/summary.csv) and the `templates/` folder for pre-built dashboards.

## License

Apache-2.0 © Your Name
