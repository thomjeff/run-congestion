# Vercel Python Serverless Function handler
from __future__ import annotations

import json
from datetime import datetime, UTC

from run_congestion.bridge import analyze_overlaps  # type: ignore
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def _bad(self, code: int, msg: str, content_type="text/plain; charset=utf-8"):
        body = msg.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            data = json.loads(raw or "{}")
        except Exception as e:
            return self._bad(400, f"Invalid JSON: {e}")

        # Normalize stepKm / step_km / step -> step_km
        step_km = data.get("stepKm", data.get("step_km", data.get("step", 0.03)))
        try:
            step_km = float(step_km)
        except Exception:
            return self._bad(400, "stepKm must be a number")

        request_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        try:
            result = analyze_overlaps(
                pace_csv=data["paceCsv"],
                overlaps_csv=data["overlapsCsv"],
                start_times=data["startTimes"],
                time_window=int(data.get("timeWindow", 60)),
                step_km=step_km,
                verbose=bool(data.get("verbose", False)),
                rank_by=data.get("rankBy", "peak_ratio"),
                segments=data.get("segments"),
            )
        except KeyError as e:
            return self._bad(400, f"Missing required field: {e}")
        except Exception as e:
            return self._bad(500, f"Server error running analysis: {e}")

        text = result.get("text", "")
        if not isinstance(text, str):
            text = str(text)

        response_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        body = text.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("X-Request-UTC", request_utc)
        self.send_header("X-StepKm-Requested", str(step_km))
        self.send_header("X-Response-UTC", response_utc)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
