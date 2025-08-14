# Hardened SOP for Per-Step Overlap Analysis

## Purpose & Parameters
This Standard Operating Procedure (SOP) defines the hardened, repeatable process for generating per-step overlap analysis between two running events.  

It ensures reproducibility, correctness, and alignment with previously validated CLI results.


- 🔍 Checking 10K vs Half from 0.00km–2.74km...
- 📝 Segment: Start to Friel
- 🟦 Overlap segment: 0.00km–2.74km (Start to Friel)
- 👥 Total in 'Half': 912 runners
- 👥 Total in '10K': 618 runners
- ⚠️ First overlap at 07:47:11 at 2.25km -> 10K Bib: 1617, Half Bib: 1618
- 📈 Interaction Intensity over segment: 4,763 (cumulative overlap events)
- 🔥 **Peak congestion**: 222 total runners at best step (16 from '10K', 206 from 'Half')
- 🔁 Unique Pairs: 1,003


**Default Parameters:**
- **Start offsets:** `10K = 440 min`, `Half = 460 min`  
- **Step size:** `0.03 km`  
- **Window size:** `60 seconds`  
- **Count method:** Distinct runners per step (not pairs)  
- **Input files:**  
  - `your_pace_data.csv` — columns: `event`, `runner_id`, `pace`, `distance`
  - `overlaps.csv` — used for segment metadata (not for per-step counts)

---

## 🔒 Hardened, One-Shot Prompt

**Instruction Set (do not deviate):**  
1. **Data & schema (must match exactly):**  
   - Load `your_pace_data.csv` with required columns: `event`, `runner_id`, `pace`, `distance`  
   - Load `overlaps.csv` for segment metadata only (not per-step counts)

2. **Computation method:**  
   - Use the exact per-step logic that matched CLI earlier:  
     `start_times = {EventA: 440, EventB: 460}`, `step_km = 0.03`, `time_window = 60s`  
   - Count separately for Event A and Event B, then sum into `combined_runners`  
   - **Do NOT** invent alternative windowing, joining, or slicing methods

3. **Scope for the run:**  
   - Events: `{Event A}` and `{Event B}` (no others)  
   - Segment: `{X.XX}–{Y.YY} km`

4. **Deliverables:**  
   - CSV: `km`, `{EventA}_runners`, `{EventB}_runners`, `combined_runners`  
   - PNG chart with three lines: `{EventA}`, `{EventB}`, `Combined`

5. **Acceptance criteria:**  
   - Peak `combined_runners` must be plausible given staggered starts  
   - First bins must not show full-field counts if later-starting event hasn’t arrived  
   - **If any criterion fails, STOP and show diagnostics — do not output final files**  
   - Report: `peak_km`, `peak_{EventA}`, `peak_{EventB}`, `peak_combined`  
   - Show first 4 rows and peak row inline

6. **File naming:**  
   - CSV: `{EventA}_vs_{EventB}_{X.XX}_{Y.YY}km_split_counts.csv`  
   - PNG: `{EventA}_vs_{EventB}_{X.XX}_{Y.YY}km_split_counts.png`

---

## ✅ Pre-run Checklist (must confirm before computing)
- [ ] Both CSVs are found  
- [ ] Detected required columns in `your_pace_data.csv`  
- [ ] Parameters locked: `start_times = {10K: 440, Half: 460}`, `step_km = 0.03`, `time_window = 60s`  
- [ ] Events filtered to `{Event A}`, `{Event B}` only (exclude unrelated events like Full)  
- [ ] Segment bounds match exactly `{X.XX}–{Y.YY} km`  
- [ ] Counting distinct runners per step (not pairs)  
- [ ] Output file names will match exactly the naming spec  
- [ ] Will show first 4 rows + peak row for audit

---

## 🖥 Quick Command Prompt (copy-paste for ChatGPT)

```
Using `your_pace_data.csv` and `overlaps.csv`, run the real computation method with:
- analyze_overlaps logic
- Start offsets: {EventA}=440 min, {EventB}=460 min
- Step size = 0.03 km
- Window size = 60s
- Distinct runner counts per step
For the segment {X.XX}–{Y.YY} km between {Event A} and {Event B}, produce:
1. CSV table with columns: km, {EventA}_runners, {EventB}_runners, combined_runners
2. Chart with three lines ({EventA}, {EventB}, Combined)
```

---

## Why this works
- The **Pre-run Checklist** forces schema and parameter validation before code execution  
- The **Do NOT** list prevents common drift from the validated method  
- The **Acceptance criteria** act as a fast sanity check so bad outputs never go unnoticed  
- Deterministic filenames keep GitHub diffs clean and unambiguous

---

## Optional Hard Gate
If known, add:
> “Peak combined must equal `{expected_value}` ± 0 at ~`{expected_km}` km; if not, stop and show diagnostics.”

---
