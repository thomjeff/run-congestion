# Overlap Analysis Instructions

This document provides a **repeatable method** for generating per-step congestion tables and charts for any overlap segment using `your_pace_data.csv` and `overlaps.csv`.

- 🔍 Checking 10K vs Half from 0.00km–2.74km...
- 📝 Segment: Start to Friel
- 🟦 Overlap segment: 0.00km–2.74km (Start to Friel)
- 👥 Total in 'Half': 912 runners
- 👥 Total in '10K': 618 runners
- ⚠️ First overlap at 07:47:11 at 2.25km -> 10K Bib: 1617, Half Bib: 1618
- 📈 Interaction Intensity over segment: 4,763 (cumulative overlap events)
- 🔥 **Peak congestion**: 222 total runners at best step (16 from '10K', 206 from 'Half')
- 🔁 Unique Pairs: 1,003

---

## **Purpose**
To provide additional context for the Peak Cogestion information provided by the Overlap Segment analysis using the exact calculation method for specific events (e.g.: 10K vs. Half) and overlap segment (0.00–2.74 km, or 5.81–8.10 km).

---

## **Required Data Files**
1. `your_pace_data.csv` — contains runner pace and event type data.
2. `overlaps.csv` — contains overlap segment start/end coordinates, event pairs, and matching logic.

---

## **Key Parameters**
- **Start time offsets**:
  - 10K → `440` minutes
  - Half → `460` minutes
- **Step size**: `0.03 km` (~30 meters)
- **Window size**: `60 seconds` for determining which runners are in the same step window.
- **Count type**: **Distinct runners** per step (not interaction pairs).

---
## Instruction Set (do not deviate):

### 1. Data & schema (must match exactly):
- Load `your_pace_data.csv` with columns: `event`, `runner_id`, `pace`, `distance`.
- Load `overlaps.csv` (do not rely on it for per-step counts; only for segment metadata if needed).

### 2. Computation method (engine semantics only):
- Run per-step congestion calculation using `analyze_overlaps` logic from `overlap.py`:
- Use the same per-step logic that matched the CLI earlier: constant pace, `start_times = {10K: 440, Half: 460}` (minutes), `step_km = 0.03`, `time_window = 60s`, distinct runner counts per step.
- Count **unique Runner IDs** separately for Event A and Event B, then sum into `combined_runners`.
- **Do NOT** invent/approximate alternative windowing, joining, or distance slicing.

### 3. Scope for this run:
- Events: `{Event A}` and `{Event B}` (no others).
- Segment: `{X.XX}–{Y.YY}` km.

### 4. Deliverables:
- CSV with columns: `km`, `{EventA}_runners`, `{EventB}_runners`, `combined_runners`.
- PNG chart with three lines: `{EventA}`, `{EventB}`, Combined.

   ```python
   import matplotlib.pyplot as plt

   plt.figure(figsize=(10,5))
   plt.plot(results_df['km'], results_df['10K_runners'], label='10K')
   plt.plot(results_df['km'], results_df['Half_runners'], label='Half')
   plt.plot(results_df['km'], results_df['combined_runners'], label='Combined', linewidth=2)
   plt.xlabel("Distance (km)")
   plt.ylabel("Runners in overlap step")
   plt.title("Per-step congestion")
   plt.legend()
   plt.grid(True)
   plt.savefig("segment_results.png", dpi=150)
   plt.close()
   ```
   
### 5. Acceptance criteria (must pass):
- Peak (max of `combined_runners`) is plausible given staggered starts; first bins must not show full-field counts when later-starting event hasn’t arrived.
- Report: `peak_km`, `peak_{EventA}`, `peak_{EventB}`, `peak_combined`.
- Show the first 4 rows and the peak row inline for quick audit.

### 6. File names:
- CSV: `{EventA}_vs_{EventB}_{X.XX}_{Y.YY}km_split_counts.csv`
- PNG: `{EventA}_vs_{EventB}_{X.XX}_{Y.YY}km_split_counts.png`

---

## Pre-run Checklist (echo this back before computing):
- [ ] Found both CSVs.
- [ ] Detected required columns in `your_pace_data.csv`: `event`, `runner_id`, `pace`, `distance`.
- [ ] Parameters locked: `start_times={10K:440, Half:460}`, `step_km=0.03`, `time_window=60s`.
- [ ] Events filtered to `{Event A}`, `{Event B}` only.
- [ ] Segment bounds `{X.XX}–{Y.YY}` km.
- [ ] Counting distinct runners per step (not pairs).
- [ ] Will output the two files with the exact names above and print first 4 rows + peak row.

---

## Why this works (no sugar-coating)
- The Pre-run Checklist forces me to validate schema and parameters before code. If anything’s off, I must stop and say so—no silent approximations.
- The “Do NOT” limits block the common drift (e.g., trying to merge on overlaps.csv or using naive distance filters).
- The Acceptance criteria give you a fast sanity check (first rows + peak row), so you don’t have to open the CSV to catch obvious nonsense.
- Deterministic filenames remove ambiguity and make your GitHub diffs clean.

---

## Optional belt-and-suspenders (add if helpful)
- Add an expected peak if you know it, to make it a hard gate:  
  “Peak combined must equal 1,250 ± 0 at ~7.XX km; if not, stop and show diagnostics.”
- Add a “re-use code” clause for absolute clarity:  
  “Re-use the same computation path you used for 0.00–2.74 km and 5.81–8.10 km that matched the CLI; do not introduce new logic.”

---

## TL;DR
Adding checklist + acceptance criteria + do-not list + fixed filenames turns it into an execution-grade SOP, so you don’t have to babysit a second segment ever again.

---

## **Quick Command Prompt**
When asking ChatGPT to generate the same analysis, use:
```
# Run overlap analysis for a specific segment and two events
# Using real computation method (matches CLI) — DO NOT approximate

# === PARAMETERS (edit these before running) ===
EVENT_A="10K"
EVENT_B="Half"
START_A=440       # start offset in minutes
START_B=460       # start offset in minutes
STEP_KM=0.03      # distance step size
WINDOW_SEC=60     # time window in seconds
KM_START=5.81
KM_END=8.10
CSV_A="your_pace_data.csv"
CSV_B="overlaps.csv"

# === EXECUTION INSTRUCTIONS ===
# 1. Load both CSVs and confirm schema:
#    your_pace_data.csv: event, runner_id, pace, distance
#    overlaps.csv: used only for metadata, not counts
# 2. Use analyze_overlaps logic:
#    - Filter to $EVENT_A and $EVENT_B only
#    - Apply start offsets ($START_A, $START_B)
#    - Step through $KM_START → $KM_END in $STEP_KM increments
#    - Count DISTINCT runners in each event within ±(WINDOW_SEC/2)
# 3. Output:
#    - CSV: ${EVENT_A}_vs_${EVENT_B}_${KM_START}_${KM_END}km_split_counts.csv
#    - PNG: ${EVENT_A}_vs_${EVENT_B}_${KM_START}_${KM_END}km_split_counts.png
# 4. Acceptance check before finalizing:
#    - Peak combined count is plausible given staggered starts
#    - First bins do not contain full-field counts unless both events have arrived
#    - Print first 4 rows and peak row for verification

# === EXAMPLE RUN ===
python run_overlap_analysis.py \
  --pace-file "$CSV_A" \
  --overlaps-file "$CSV_B" \
  --event-a "$EVENT_A" \
  --event-b "$EVENT_B" \
  --start-a "$START_A" \
  --start-b "$START_B" \
  --step-km "$STEP_KM" \
  --window-sec "$WINDOW_SEC" \
  --km-start "$KM_START" \
  --km-end "$KM_END" \
  --output-csv "${EVENT_A}_vs_${EVENT_B}_${KM_START}_${KM_END}km_split_counts.csv" \
  --output-png "${EVENT_A}_vs_${EVENT_B}_${KM_START}_${KM_END}km_split_counts.png"

```
Confirm EVENT_A, EVENT_B, START_A and START_B, KM_START and KM_END values with your desired segment info.

---

## **Template Output**
- `segment_results.csv`
- `segment_results.png`

---

## **Notes**
- Always filter **out unrelated events** (e.g., Full) before running the counts.
- Ensure the segment boundaries match exactly to the values in `overlaps.csv`.
- The method counts **presence in a slice**, not interaction pairs.
