# Back-End API Requirements

This document specifies the requirements for a Vercel-hosted back-end API (“run-congestion API”) that exposes the existing `detect_overlap.py` logic to a Wix front-end.

---

## 1. Architecture Overview

- **Platform**: Serverless functions on Vercel (Python 3 runtime).  
- **Data storage**:  
  - `data/your_pace_data.csv`  
  - `data/overlaps.csv`  
- **Client**: Wix front-end collects parameters, posts JSON to the API, and renders the returned report.

---

## 2. API Endpoints

### **POST** `/api/v1/detect-overlap`

#### Purpose
Run the congestion analysis on one or more overlapping segments and return both a formatted text report and structured JSON summary.

#### Request

- **Headers**

Content-Type: application/json
Accept: application/json

- **Body**

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

Response
  • 200 OK

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
    },
    …
  ]
}

• 4XX / 5XX

{
  "success": false,
  "error": "Missing required field: overlapsCsvPath"
}

3. Functional Requirements
  1.  Input validation
  • Ensure CSV paths (or URLs) exist and contain required columns.
  • Verify startTimes covers every event in overlaps.csv.
  • Validate numeric parameters: timeWindow > 0, stepKm > 0.
  2.  CSV loading
  • Parse both CSVs into pandas DataFrames.
  3.  Core computation
  • For each segment in overlaps.csv, invoke the vectorized detect_segment_overlap function.
  • Honor verbose flag to include per-segment detail.
  4.  Ranking
  • Sort segments by peak_ratio or intensity based on rankBy.
  5.  Output assembly
  • Build reportText string matching CLI formatting.
  • Build typed JSON summary array for front-end display.
  6.  Error handling
  • Return HTTP 400 for client errors, HTTP 500 for server errors.
  • Include clear, actionable messages.

⸻

4. Non-Functional Requirements
  • Performance:
  • ≤ 3 s for typical runs (1–3 segments).
  • ≤ 10 s for larger analyses.
  • CORS: Allow origin of your Wix site (e.g. https://your-site.wixsite.com).
  • Rate limiting: Throttle to ~ 10 requests/minute/IP.
  • Logging & monitoring:
  • Record inputs, execution time, errors in Vercel logs.
  • Versioning:
  • All endpoints under /api/v1/....
  • Bump to /api/v2/... for breaking changes.

⸻

5. Next Steps
  1.  Prototype a single serverless function (FastAPI or Flask) on Vercel.
  2.  Test with Postman or curl against the new endpoint.
  3.  Integrate into Wix via fetch(); render reportText in a <pre> block initially.
  4.  Enhance UI to parse the summary JSON and display sortable tables or charts.

# Example invocation from Wix front-end
fetch("https://run-congestion.vercel.app/api/v1/detect-overlap", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    paceCsvPath: "/static/data/your_pace_data.csv",
    overlapsCsvPath: "/static/data/overlaps.csv",
    startTimes: { Full: 420, "10K": 440, Half: 460 },
    timeWindow: 60,
    stepKm: 0.01,
    verbose: true,
    rankBy: "peak_ratio"
  })
})
.then(r => r.json())
.then(data => displayReport(data.reportText))

Versioned as part of run-congestion v1.0.0.

