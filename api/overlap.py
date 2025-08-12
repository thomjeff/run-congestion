
import json
import traceback
from http import HTTPStatus
from run_congestion.engine import analyze_overlaps

# Stateless API for Vercel (no Blob, no storage). Reads CSVs from URLs and returns text.
# POST /api/overlap
# Body:
# {
#   "paceCsv": "https://.../your_pace_data.csv",
#   "overlapsCsv": "https://.../overlaps.csv",
#   "startTimes": {"Full": 420, "10K": 440, "Half": 460},
#   "timeWindow": 60,
#   "stepKm": 0.03,
#   "verbose": true,
#   "rankBy": "peak_ratio"  # or "intensity"
# }

def _bad_request(msg: str):
    return {
        "statusCode": HTTPStatus.BAD_REQUEST,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": msg})
    }

def _ok_text(text: str):
    return {
        "statusCode": HTTPStatus.OK,
        "headers": {"Content-Type": "text/plain; charset=utf-8"},
        "body": text
    }

def handler(request, response):
    try:
        if request.method != "POST":
            return _bad_request("Use POST with JSON body.")

        try:
            payload = request.get_json() if hasattr(request, "get_json") else json.loads(request.body or "{}")
        except Exception as e:
            return _bad_request(f"Invalid JSON: {str(e)}")

        # Required inputs
        pace_csv = payload.get("paceCsv")
        overlaps_csv = payload.get("overlapsCsv")
        start_times = payload.get("startTimes")
        if not pace_csv or not overlaps_csv or not start_times:
            return _bad_request("Missing one of: paceCsv, overlapsCsv, startTimes")

        # Optional params
        time_window = int(payload.get("timeWindow", 60))
        step_km = float(payload.get("stepKm", 0.03))
        verbose = bool(payload.get("verbose", False))
        rank_by = payload.get("rankBy", "peak_ratio")

        # Guardrails for Hobby tier timeouts
        if step_km < 0.03:
            step_km = 0.03

        out = analyze_overlaps(
            pace_path=pace_csv,
            overlaps_path=overlaps_csv,
            start_times=start_times,
            time_window_secs=time_window,
            step_km=step_km,
            verbose=verbose,
            rank_by=rank_by,
            # Explicitly disable any storage writes
            write_summary_csv=None
        )

        return _ok_text(out["text"])

    except Exception as e:
        tb = traceback.format_exc()
        return {
            "statusCode": HTTPStatus.INTERNAL_SERVER_ERROR,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(e), "trace": tb})
        }
