# Run Congestion Analysis — Density-Based Requirements

This document captures the requirements and proposed CLI/API outputs for replacing the legacy concepts
(`Peak congestion`, `Interaction Intensity`) with density-based measures that better reflect *crowding*
on uni/bi-directional trail segments.

---

## 1. Background

The previous implementation reported:
- **Peak congestion**: combined runner counts at a step.
- **Interaction Intensity**: cumulative overlap events.

These were difficult for non-technical stakeholders to interpret.  
The new approach pivots to **density-based KPIs** grounded in runners per square metre (areal) and runners per metre (linear).

---

## 2. Data Dependencies

- `your_pace_data.csv` — pacing and bib-level splits for all participants.
- `overlaps.csv` — computed overlap windows between event pairs (10K vs Half, etc.).  
  → This logic must be incorporated into the new scripts so users don’t have to provide it manually.

---

## 3. Script Updates

- **`engine.py` / `overlap.py` → new `density.py`**
  - Compute peak step density (`/m²`, `/m`).
  - Compute segment-average density at concurrency peak.
  - Split density zones by thresholds (<1.0, 1.0–1.5, 1.5–2.0, ≥2.0 /m²).
  - Handle uni vs bi-directional trail geometry (bi uses half-width per lane, normalized results reported for comparability).
- Clean up unused files: `io_cache`, `L2_blob` (no longer needed under Vercel Hobby).

---

## 4. Outputs

Two formats must be supported:

1. **CLI logs** — human-readable, in the style of the current tool.
2. **API JSON payloads** — machine-consumable, aligned with CLI values.

---

## 5. Example Segments

### A) 10K + Half — 0.00–2.74 km (uni, width=3.0 m)

#### CLI
```
🔍 Checking 10K vs Half from 0.00km–2.74km...
📝 Segment: Start → Friel (shared outbound, uni-directional)
🟦 Geometry: length=2.74 km, width=3.0 m
👥 Peak concurrent: 222 (10K=16, Half=206) @ 2.73 km
📈 Density (peak step): 2.47 /m²  (Linear ≈ 7.4 /m)
📉 Density (segment-average @ concurrency peak): 0.03 /m² (Linear ≈ 0.09 /m)

🚦 Distance in density zones (by km):
   Green   (<1.0): 2.60 km  (94.9%)
   Amber (1.0–1.5): 0.00 km  (0.0%)
   Red   (1.5–2.0): 0.06 km  (2.2%)
   Dark-Red (≥2.0): 0.09 km  (3.3%)

✅ Flow status: Comfortable overall; short-lived crest at the merge front.
```

#### API JSON
```json
{
  "segment": {"from_km": 0.00, "to_km": 2.74, "name": "Start→Friel"},
  "geometry": {"width_m": 3.0, "direction": "uni"},
  "concurrency": {"10K": 16, "Half": 206, "combined": 222, "peak_km": 2.73},
  "density": {
    "peak_step_areal_m2": 2.47,
    "peak_step_linear_m": 7.4,
    "segment_avg_at_peak_areal_m2": 0.03,
    "segment_avg_at_peak_linear_m": 0.09
  },
  "zones_km": {"green": 2.60, "amber": 0.00, "red": 0.06, "dark_red": 0.09},
  "index": {"congestion_0_10": 1.2, "version": "v1"}
}
```

---

### B) 10K only — 2.74–5.80 km (bi, width=1.5 m per lane)

#### CLI
```
🔍 Checking 10K (bi-directional) from 2.74km–5.80km...
📝 Segment: Trail turnaround corridor (two-way lanes)
🟦 Geometry: length=3.06 km, width=1.5 m per lane (bi)
👥 Peak concurrent: 614 (all 10K) across both directions
📈 Density (peak step, normalized to 3.0 m ref): 1.34 /m²  (Linear ≈ 4.0 /m)
📉 Density (segment-average @ concurrency peak): 0.13 /m² (Linear ≈ 0.20 /m)

🚦 Distance in density zones (normalized, by km):
   Green   (<1.0): 3.06 km (100%)
   Amber (1.0–1.5): 0.00 km (0%)
   Red   (1.5–2.0): 0.00 km (0%)
   Dark-Red (≥2.0): 0.00 km (0%)

✅ Flow status: Comfortable — two-way flow manageable at peak.
```

#### API JSON
```json
{
  "segment": {"from_km": 2.74, "to_km": 5.80, "name": "Friel→10K Turn"},
  "geometry": {"width_m": 1.5, "direction": "bi"},
  "concurrency": {"10K": 614, "Half": 0, "combined": 614},
  "density": {
    "peak_step_areal_m2_normalized": 1.34,
    "peak_step_linear_m_normalized": 4.0,
    "segment_avg_at_peak_areal_m2": 0.13,
    "segment_avg_at_peak_linear_m": 0.20
  },
  "zones_km_normalized": {"green": 3.06, "amber": 0.00, "red": 0.00, "dark_red": 0.00},
  "index": {"congestion_0_10": 2.0, "version": "v1"}
}
```

---

### C) 10K + Half — 5.81–8.10 km (uni, width=3.0 m)

#### CLI
```
🔍 Checking 10K vs Half from 5.81km–8.10km...
📝 Segment: Friel → Station/Barker (shared return, uni-directional)
🟦 Geometry: length=2.29 km, width=3.0 m
👥 Peak concurrent: 1,250 (10K=355, Half=895) near 8.09 km
📈 Density (peak step): 2.52 /m²  (Linear ≈ 7.6 /m)
📉 Density (segment-average @ concurrency peak): 0.18 /m² (Linear ≈ 0.55 /m)

🚦 Distance in density zones (by km):
   Green   (<1.0): 0.00 km (0%)
   Amber (1.0–1.5): 0.00 km (0%)
   Red   (1.5–2.0): 0.00 km (0%)
   Dark-Red (≥2.0): 2.29 km (100%)

⚠️ Flow status: Sustained high density — platooning likely; passing limited.
```

#### API JSON
```json
{
  "segment": {"from_km": 5.81, "to_km": 8.10, "name": "Friel→Station/Barker"},
  "geometry": {"width_m": 3.0, "direction": "uni"},
  "concurrency": {"10K": 355, "Half": 895, "combined": 1250, "peak_km": 8.09},
  "density": {
    "peak_step_areal_m2": 2.52,
    "peak_step_linear_m": 7.6,
    "segment_avg_at_peak_areal_m2": 0.18,
    "segment_avg_at_peak_linear_m": 0.55
  },
  "zones_km": {"green": 0.00, "amber": 0.00, "red": 0.00, "dark_red": 2.29},
  "index": {"congestion_0_10": 5.2, "version": "v1"}
}
```

---

## 6. Implementation Notes

- Keep both density numbers:
  - `peak_step_*` = what the runner feels at the crest (step-level, short-lived congestion).
  - `segment_avg_at_peak_*` = severity normalized over the full segment geometry.
- **Zones** are computed at step-level then aggregated to distances.
- Bi-directional segments must calculate per-lane width but expose normalized values for comparability.

---

## 7. Next Steps

- Wire new `density.py` logic into CLI + API.
- Update tests to validate peak density, segment averages, and zone distances.
- Remove legacy files no longer needed in deployment (`io_cache`, `L2_blob`).
