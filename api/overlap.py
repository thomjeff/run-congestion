import os
import json
import tempfile
import base64
import urllib.request
import traceback

from run_congestion.engine import analyze_overlaps, parse_start_times

def handler(request):
    try:
        if request.method != "POST":
            return {
                "statusCode": 405,
                "headers": {"Allow": "POST"},
                "body": "Method Not Allowed"
            }

        payload = request.get_json()
        pace_src     = payload["paceCsv"]
        overlaps_src = payload["overlapsCsv"]
        start_times  = payload["startTimes"]
        time_window  = int(payload.get("timeWindow", 60))
        step_km      = float(payload.get("stepKm", 0.01))
        verbose      = bool(payload.get("verbose", False))
        rank_by      = payload.get("rankBy", "peak_ratio")

        def _fetch_csv(src: str, suffix: str) -> str:
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            path = tf.name
            try:
                if src.startswith(("http://", "https://")):
                    urllib.request.urlretrieve(src, path)
                else:
                    tf.write(base64.b64decode(src))
            finally:
                tf.close()
            # Debug: confirm file exists and size
            if not os.path.exists(path):
                raise FileNotFoundError(f"Temp file not found after fetch: {path}")
            size = os.path.getsize(path)
            if size == 0:
                raise IOError(f"Fetched file is empty: {path}")
            return path

        pace_path     = _fetch_csv(pace_src, ".csv")
        overlaps_path = _fetch_csv(overlaps_src, ".csv")

        if isinstance(start_times, list):
            start_times = parse_start_times(start_times)

        # Run analysis
        report_text, summary = analyze_overlaps(
            pace_path, overlaps_path, start_times,
            time_window=time_window,
            step_km=step_km,
            verbose=verbose,
            rank_by=rank_by
        )

        # Cleanup
        for fp in (pace_path, overlaps_path):
            try:
                os.remove(fp)
            except Exception:
                # Log but don't fail cleanup
                print(f"Warning: could not remove temp file {fp}", file=sys.stderr)

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
        tb = traceback.format_exc()
        print("🚨 /api/overlap error:\n", tb, file=sys.stderr)
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "success": False,
                "error":   str(e),
                "trace":   tb
            })
        }
