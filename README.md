![alt text](/images/repo-image.jpg)

# Race Congestion Detection - README

## Overview
This tool analyzes overlapping race events (e.g., 10K, Half, Full) to identify **acute bottlenecks** and sustained interaction zones by comparing runners' arrival times on shared course segments. It uses runner pace and event start times to compute overlaps and ranks segments either by **acute severity (peak ratio)** or **total interaction volume (intensity)**.

## Key Concepts

### Intensity
Cumulative count of overlapping events across the entire segment. At each distance step (default 0.01 km), every pair of runners (one from each event) whose arrival times at that point differ by no more than the `--time-window` (seconds) contributes one to intensity. This reflects total “interaction work” and is influenced by segment length and field sizes.

### Intensity per km
`intensity / segment_length`. Normalizes intensity by distance to highlight dense interactions on shorter segments.

### Peak Congestion
Maximum number of distinct runners (sum of both events) simultaneously overlapping at any single distance step within the segment. Highlights instantaneous crowding.

### Peak Ratio
`peak_congestion / (total_prev + total_curr)`. Ratio of the peak congested cohort to the combined field size. This is the acute bottleneck metric; higher values indicate a larger proportion of the participants are in conflict at peak.

## File Inputs

### your_pace_data.csv
Columns (case-insensitive):
- `event`: Event name (e.g., Full, Half, 10K)
- `runner_id`: Unique identifier for a runner (synthetic IDs starting at 1000 recommended)
- `pace`: Pace in minutes per kilometer (do **not** convert from seconds; keep as min/km)
- `distance`: Total event distance (used for filtering, can be kept per runner if consistent)

### overlaps.csv
Defines overlapping segments. Required columns:
- `event`: Earlier-start event (prev_event)
- `start`: Segment start in km (float)
- `end`: Segment end in km (float)
- `overlapswith`: Later-start event (curr_event)
- `description`: (optional) human-readable label for the segment

Example row:
```
Full,29.03,37.00,Half,"Full return leg"
```

## Usage

Make the script executable (permissions issue encountered if omitted):
```bash
chmod +x detect_overlap.py
```
If you get `zsh: permission denied: ./detect_overlap.py`, ensure:
- Executable bit is set (use `chmod +x detect_overlap.py`)
- You're in the correct directory containing the script
- You invoke with `./detect_overlap.py` or `python ./detect_overlap.py`

Run analysis:
```bash
python ./detect_overlap.py your_pace_data.csv overlaps.csv   --start-times Full=420 10K=440 Half=460   --time-window 60 --step 0.01 --verbose   --export-summary summary.csv
```

### Flags
- `--start-times` / `-s`: Required. Event start times in minutes since midnight (e.g., `Full=420` is 7:00 AM).  
- `--time-window`: Seconds tolerance for declaring an overlap (default 60).  
- `--step`: Distance resolution in km (default 0.01 = 10 meters). Smaller increases accuracy at cost of runtime.  
- `--verbose`: Print detailed per-segment output with descriptions and runtime.  
- `--export-summary`: Path to output CSV with full summary.  
- `--rank-by`: Ranking metric for summary. Choices: `intensity` or `peak_ratio`. Default is `peak_ratio` to focus on acute bottlenecks.

## Output
Console output includes:
- Segment-by-segment breakdown:
  - Overlap segment and description  
  - Field sizes (`total_prev` / `total_curr`)  
  - First overlap (time, km, bibs)  
  - Interaction Intensity (cumulative events)  
  - Peak congestion and its composition  
  - Unique overlapping pairs  
  - Segment runtime  

- Summary table ranked by the chosen metric (peak ratio or intensity), showing:
  - `PeakRatio`, `Peak`, `Intensity/km`, `Intensity`, `DistinctPairs`, segment description.

- CSV (`summary.csv`) contains detailed columns for dashboard ingestion, including metadata (start times, window, first overlap details, runtime, etc.)

## Suggested Dashboard Ingestion
- Load `summary.csv` into Excel via Data > From Text/CSV.  
- Format `peak_congestion_ratio` as percentage.  
- Pivot or sort by `PeakRatio` to surface acute bottlenecks.  
- Visualizations: bar chart of top segments by PeakRatio, scatter plot of `Intensity/km` vs `PeakRatio` with bubble size = `peak_congestion`.  
- Drill-in: display first overlap details, field sizes, and segment description for chosen hotspots.

## Troubleshooting

- **Permission denied executing script:** Run `chmod +x detect_overlap.py` and ensure you're calling `./detect_overlap.py` from the folder containing it.  
- **Missing input file error (e.g., overlaps.csv):** Verify filenames are correct, paths are relative to current directory, and spelling/casing matches.  
- **Slow performance:** The default logic is vectorized for speed, but high runner counts and small `--step` increase compute. Consider increasing `--step` to 0.02 or 0.05 for exploratory runs.  
- **Metric confusion:**  
  - Use `--rank-by peak_ratio` to prioritize acute bottlenecks (default).  
  - Use `--rank-by intensity` to see hotspots with the most total interaction volume.

## Example Interpretation

```
01. Full vs 10K 16.00km–20.52km (Full/10K Friel to Queen Sq. Loop): PeakRatio=83.47%, Peak=823, Intensity/km=286174.8, Intensity=1,293,510, DistinctPairs=9,811
```
Meaning: At that segment, 83.47% of the combined field was simultaneously overlapping at peak; the worst point had 823 runners involved. The volume of interactions normalized per km is high, indicating both acute and sustained risk.

## Next Steps / Enhancements
- Integrate with Excel dashboard (linked charts) for refreshable reporting.  
- Add automated alerts for segments exceeding a PeakRatio threshold.  
- Batch-run variation analyses by adjusting start times or time window to simulate mitigation strategies.

## Versioning / Audit
Include the `generated_at` timestamp from the CSV to track when the analysis was created, along with the exact parameters (`start_prev`, `start_curr`, `time_window`, `step`, `rank-by`) embedded in the export.

## Recent Fixes / Gotchas
- **Execution permission issue:** If you see `zsh: permission denied: ./detect_overlap.py`, run `chmod +x detect_overlap.py` or invoke the script directly with Python:  
  ```bash
  python ./detect_overlap.py ...
  ```  
  This avoids macOS execution-bit or quarantine oddities.
- **Datetime timezone error:** Earlier versions used `datetime.now(datetime.timezone.utc)`, which failed in some environments. The script now uses `from datetime import datetime, timezone` and `datetime.now(timezone.utc).isoformat()` to produce a proper UTC timestamp.  
- **JSONL export removed:** The script no longer has `--export-json`; only `--export-summary` (CSV) is supported, simplifying downstream ingestion.

## Summary Dashboard & Template Files (what you downloaded)
Two Excel artifacts were provided to accelerate analysis and reporting:

### 1. `summary_template.xlsx`
A lightweight ingestion template:
- Sheet **Data Template** contains all required headers matching the exported `summary.csv`.  
- Example row with placeholder values.  
- Instructions for:
  - Turning `PeakRatio` into a percentage.  
  - Computing `SeverityScore` (`=PeakRatio * Intensity_per_km`).  
  - Ranking by PeakRatio and Intensity using Excel formulas (`RANK.EQ`).  
  - Building pivot tables and visualizations.

### 2. `summary_dashboard.xlsx`
A prebuilt dashboard workbook:
- Sheet **Raw Data** with sample overlapping segment data.  
- Sheet **Summary Table** with computed ranks (`Rank_PeakRatio`, `Rank_Intensity`), `SeverityScore`, and key metrics arranged for stakeholder consumption.  
- Charts included:  
  - **Bar chart** showing top segments by `PeakRatio`.  
  - **Scatter plot** comparing `Intensity_per_km` vs `PeakRatio` (used as a proxy for bubble chart, since bubble sizing required manual refinement).  
- Designed to be the basis for executive slides: you can copy/paste or link these charts into PowerPoint or Word for refreshable reporting.

### Recommended workflow with those files
1. Run the updated script to produce `summary.csv`.  
2. Open `summary_dashboard.xlsx` and replace the sample rows on **Raw Data** with your real `summary.csv` content (or load via copy/paste).  
3. On **Summary Table**, the computed ranks and severity will auto-update if you keep the same column structure.  
4. Use the existing charts, or build new ones, to highlight acute bottlenecks (sorted by `PeakRatio`) and compare density vs volume.

