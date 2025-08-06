import os
import json
import tempfile
import base64
import urllib.request

from http.server import BaseHTTPRequestHandler
from run_congestion.engine import analyze_overlaps, parse_start_times

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Parse request body
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        # Extract parameters
        try:
            pace_src     = payload["paceCsv"]
            overlaps_src = payload["overlapsCsv"]
            start_times  = payload["startTimes"]
            time_window  = int(payload.get("timeWindow", 60))
            step_km      = float(payload.get("stepKm", 0.01))
            verbose      = bool(payload.get("verbose", False))
            rank_by      = payload.get("rankBy", "peak_ratio")
        except (KeyError, ValueError) as e:
            self.send_error(400, f"Missing or invalid field: {e}")
            return

        # Materialize CSVs to temp files
        def _fetch_csv(src: str, suffix: str) -> str:
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            path = tf.name
            if src.startswith("http://") or src.startswith("https://"):
                urllib.request.urlretrieve(src, path)
            else:
                tf.write(base64.b64decode(src))
            tf.close()
            return path

        try:
            pace_path     = _fetch_csv(pace_src, ".csv")
            overlaps_path = _fetch_csv(overlaps_src, ".csv")
            if isinstance(start_times, list):
                start_times = parse_start_times(start_times)

            report_text, summary = analyze_overlaps(
                pace_path,
                overlaps_path,
                start_times,
                time_window=time_window,
                step_km=step_km,
                verbose=verbose,
                rank_by=rank_by
            )

            # Clean up
            os.remove(pace_path)
            os.remove(overlaps_path)

        except Exception as e:
            # Internal server error
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            body = {"success": False, "error": str(e)}
            self.wfile.write(json.dumps(body).encode())
            return

        # Success response
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        response = {"success": True, "reportText": report_text, "summary": summary}
        self.wfile.write(json.dumps(response).encode())
