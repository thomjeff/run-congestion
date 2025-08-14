# Overlap Analysis Instructions

This document provides a **repeatable method** for generating per-step congestion tables and charts for any overlap segment using `your_pace_data.csv` and `overlaps.csv`.

---

## **Purpose**
To replicate the exact calculation method used for the 0.00–2.74 km and 5.81–8.10 km **10K vs Half** overlap segments.

---

## **Required Inputs**
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

## **Exact Steps to Run**

1. **Load CSV data**:
   ```python
   import pandas as pd

   pace_df = pd.read_csv("your_pace_data.csv")
   overlaps_df = pd.read_csv("overlaps.csv")
   ```

2. **Filter to desired segment** (example: `10K vs Half`, `5.81–8.10 km`):
   ```python
   segment = overlaps_df[
       (overlaps_df['event1'] == '10K') &
       (overlaps_df['event2'] == 'Half') &
       (overlaps_df['start_km'] == 5.81) &
       (overlaps_df['end_km'] == 8.10)
   ].iloc[0]
   ```

3. **Run per-step congestion calculation** using `analyze_overlaps` logic from `overlap.py`:
   - Apply start offsets for events.
   - Iterate in 0.03 km increments from `segment.start_km` to `segment.end_km`.
   - Count **unique runner IDs** from each event whose race time passes through that slice within the 60-second window.
   - Store:
     - `10K_runners`
     - `Half_runners`
     - `combined_runners` = sum of both.

4. **Save table**:
   ```python
   results_df.to_csv("segment_results.csv", index=False)
   ```

5. **Generate chart**:
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

---

## **Quick Command Prompt**
When asking ChatGPT to generate the same analysis, use:
```
Using `your_pace_data.csv` and `overlaps.csv`, run the real computation method with:
- analyze_overlaps logic
- Start offsets: 10K=440 min, Half=460 min
- Step size = 0.03 km
- Window size = 60s
- Distinct runner counts per step
For the segment [X]–[Y] km between [Event A] and [Event B], produce:
1. CSV table with columns: km, EventA_runners, EventB_runners, combined_runners
2. Chart with three lines (EventA, EventB, Combined)
```
Replace `[X]`, `[Y]`, `[Event A]`, `[Event B]` with your desired segment info.

---

## **Template Output**
- `segment_results.csv`
- `segment_results.png`

---

## **Notes**
- Always filter **out unrelated events** (e.g., Full) before running the counts.
- Ensure the segment boundaries match exactly to the values in `overlaps.csv`.
- The method counts **presence in a slice**, not interaction pairs.
