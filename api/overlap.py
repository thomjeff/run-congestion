import os
import json
import tempfile
import base64
import urllib.request
import traceback

from run_congestion.engine import analyze_overlaps, parse_start_times

def app(environ, start_response):
    try:
        # Only POST allowed
        method = environ.get("REQUEST_METHOD", "")
        if method != "POST":
            start_response("405 Method Not Allowed", [("Allow", "POST")])
            return [b""]

        # Read JSON body
        try:
            length = int(environ.get("CONTENT_LENGTH", 0))
            body = environ["wsgi.input"].read(length)
            payload = json.loads(body)
        except Exception as ex:
            start_response("400 Bad Request", [("Content-Type", "text/plain")])
            return [f"Invalid JSON: {ex}".encode()]

        # Extract parameters
        pace_src     = payload.get("paceCsv")
        overlaps_src = payload.get("overlapsCsv")
        start_times  = payload.get("startTimes")
        time_window  = int(payload.get("timeWindow", 60))
        step_km      = float(payload.get("stepKm", 0.01))
        verbose      = bool(payload.get("verbose", False))
        rank_by      = payload.get("rankBy", "peak_ratio")

        if not (pace_src and overlaps_src and start_times):
            start_response("400 Bad Request", [("Content-Type", "text/plain")])
            return [b"Missing required fields"]

        # Helper: fetch or decode CSV into temp file
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
            # Validate file
            size = os.path.getsize(path)
            if size == 0:
                raise IOError(f"Fetched file is empty: {path}")
            return path

        pace_path = _fetch_csv(pace_src, ".csv")
        overlaps_path = _fetch_csv(overlaps_src, ".csv")

        if isinstance(start_times, list):
            start_times = parse_start_times(start_times)

        # Run the core analysis
        report_text, summary = analyze_overlaps(
            pace_path, overlaps_path, start_times,
            time_window=time_window,
            step_km=step_km,
            verbose=verbose,
            rank_by=rank_by
        )

        # Cleanup
        try:
            os.remove(pace_path)
            os.remove(overlaps_path)
        except OSError:
            pass

        # Respond JSON
        start_response("200 OK", [("Content-Type", "application/json")])
        response = {"success": True, "reportText": report_text, "summary": summary}
        return [json.dumps(response).encode("utf-8")]

    except Exception:
        tb = traceback.format_exc()
        start_response("500 Internal Server Error", [("Content-Type", "application/json")])
        error_body = {"success": False, "error": "Server error", "trace": tb}
        return [json.dumps(error_body).encode("utf-8")]
