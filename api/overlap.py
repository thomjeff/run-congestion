import os
import json
import tempfile
import base64
import urllib.request

from run_congestion.engine import analyze_overlaps, parse_start_times

def handler(request):
    # 1) Enforce POST
    if request.method != "POST":
        return {
            "statusCode": 405,
            "headers": {"Allow": "POST"},
            "body": "Method Not Allowed"
        }

    # 2) Parse JSON payload
    try:
        payload = request.get_json()
        pace_src     = payload["paceCsv"]
        overlaps_src = payload["overlapsCsv"]
        start_times  = payload["startTimes"]
        time_window  = int(payload.get("timeWindow", 60))
        step_km      = float(payload.get("stepKm", 0.01))
        verbose      = bool(payload.get("verbose", False))
        rank_by      = payload.get("rankBy", "peak_ratio")
    except (KeyError, ValueError) as ie:
        return {
            "statusCode": 400,
            "body": json.dumps({"success": False, "error": f"Invalid payload: {ie}"})
        }

    # 3) Helper to materialize a CSV (URL or Base64) → temp file
    def _fetch_csv(src: str, suffix: str) -> str:
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        path = tf.name
        if src.startswith("http://") or src.startswith("https://"):
            urllib.request.urlretrieve(src, path)
        else:
            data = base64.b64decode(src)
            tf.write(data)
        tf.close()
        return path

    try:
        pace_path     = _fetch_csv(pace_src, ".csv")
        overlaps_path = _fetch_csv(overlaps_src, ".csv")

        # 4) Convert start_times if passed as list of "Event=minutes"
        if isinstance(start_times, list):
            start_times = parse_start_times(start_times)

        # 5) Delegate to your engine
        report_text, summary = analyze_overlaps(
            pace_path,
            overlaps_path,
            start_times,
            time_window=time_window,
            step_km=step_km,
            verbose=verbose,
            rank_by=rank_by
        )

        # 6) Clean up temp files
        os.remove(pace_path)
        os.remove(overlaps_path)

        # 7) Return JSON response
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "success":    True,
                "reportText": report_text,
                "summary":    summary
            })
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"success": False, "error": str(e)})
        }