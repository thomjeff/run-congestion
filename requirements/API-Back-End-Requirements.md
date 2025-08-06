# Back-End API Requirements

This document specifies the requirements for a Vercel-hosted back-end API (“run-congestion API”) that exposes the existing `detect_overlap.py` logic to a Wix front-end.

---

## 1. Architecture Overview

- **Platform**: Serverless functions on Vercel (Python 3 runtime).  
- **Data storage**:  
  - `data/your_pace_data.csv`  
  - `data/overlaps.csv`  
- **Client**: Wix front-end collects parameters, POSTs JSON to the API, and renders the returned report.

---

## 2. API Endpoints

### **POST** `/api/v1/detect-overlap`

#### Purpose
Run the congestion analysis on one or more overlapping segments and return both a formatted text report and a structured JSON summary for programmatic consumption.

#### Request

- **Headers**

  ```http
  Content-Type: application/json
  Accept: application/json
  ```

- **Body** (JSON)

  ```json
  {
    "paceCsvPath": "data/your_pace_data.csv",
    "overlapsCsvPath": "data/overlaps.csv",
    "startTimes": {
      "Full": 420,
      "10K": 440,
      "Half": 460
    },
    "timeWindow": 60,
    "stepKm": 0.01,
    "verbose": true,
    "rankBy": "peak_ratio"   // or "intensity"
  }
  ```

#### Response

- **200 OK**

  ```json
  {
    "success": true,
    "reportText": "🔍 Checking 10K vs Half from 0.00km to 2.74km…\n📝 Segment: Start to Friel\n…🗂️ Interaction Intensity Summary…",
    "summary": [
      {
        "prevEvent": "10K",
        "currEvent": "Half",
        "segment": "0.00km–2.74km",
        "description": "Start to Friel",
        "firstOverlapTime": "07:47:04",
        "firstOverlapKm": 2.24,
        "intensity": 14270,
        "intensityPerKm": 5208.0,
        "distinctPairs": 1050,
        "peakCongestion": 234,
        "peakRatio": 0.1529
      }
      // … additional segments …
    ]
  }
  ```

- **4XX / 5XX**

  ```json
  {
    "success": false,
    "error": "Missing required field: overlapsCsvPath"
  }
  ```

---

## 3. Functional Requirements

1. **Input Validation**
   - CSV paths (or URLs) must exist and contain required columns (`event`, `runner_id`, `pace`, `distance` in pace file; `event`, `start`, `end`, `overlapswith`, `description` in overlaps file).
   - `startTimes` must include every event in `overlaps.csv`.
   - `timeWindow` > 0, `stepKm` > 0.
2. **CSV Loading**
   - Parse both CSVs into pandas DataFrames.
3. **Core Computation**
   - Invoke the vectorized `detect_segment_overlap` function for each defined segment.
   - Honor the `verbose` flag to include per-segment detail.
4. **Ranking**
   - Sort segments by `peak_ratio` or `intensity` based on `rankBy`.
5. **Output Assembly**
   - Construct `reportText` (multiline string) following CLI formatting.
   - Construct typed JSON `summary` array for front-end.
6. **Error Handling**
   - Return HTTP 400 for client errors; HTTP 500 for server errors.
   - Provide clear, actionable error messages.

---

## 4. Non-Functional Requirements

- **Performance**: ≤ 3 s for 1–3 segments; ≤ 10 s for larger analyses.
- **CORS**: Allow origin of your Wix site (e.g. `https://your-site.wixsite.com`).
- **Rate Limiting**: Throttle to ~10 requests/minute per IP.
- **Logging & Monitoring**: Log inputs, execution time, and errors in Vercel logs.
- **Versioning**: All endpoints under `/api/v1/...`; bump to `/api/v2/...` for breaking changes.

---

## 5. Next Steps

1. Prototype a serverless function (e.g. FastAPI) on Vercel.
2. Test via Postman or `curl` against the new endpoint.
3. Integrate into Wix via `fetch()`; render `reportText` in a `<pre>` block.
4. Enhance UI to parse the `summary` JSON and display sortable tables/charts.

*Versioned as part of `run-congestion` v1.0.0.*
