import json
import time
from http.server import BaseHTTPRequestHandler
from run_congestion.bridge import analyze_overlaps

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        data = json.loads(body.decode("utf-8"))

        pace_csv = data.get("paceCsv")
        overlaps_csv = data.get("overlapsCsv")
        start_times = data.get("startTimes", {})
        time_window = data.get("timeWindow", 60)
        step_km = data.get("stepKm", 0.03)
        verbose = data.get("verbose", False)
        rank_by = data.get("rankBy", "peak_ratio")
        segments = data.get("segments")

        hdrs = {
            "Content-Type": "text/plain; charset=utf-8",
            "X-Request-UTC": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "X-Events-Seen": ",".join(start_times.keys()),
            "X-StepKm": str(step_km),
        }

        t0 = time.perf_counter()
        try:
            result = analyze_overlaps(
                pace_csv=pace_csv,
                overlaps_csv=overlaps_csv,
                start_times=start_times,
                time_window=time_window,
                step_km=step_km,
                verbose=verbose,
                rank_by=rank_by,
                segments=segments,
            )
        except Exception as e:
            hdrs["X-Compute-Seconds"] = f"{time.perf_counter() - t0:.2f}"
            self.send_response(500)
            for k, v in hdrs.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        elapsed = time.perf_counter() - t0
        hdrs["X-Compute-Seconds"] = f"{elapsed:.2f}"

        text = result.get("text", "") if isinstance(result, dict) else str(result)
        text = f"{text}\n⏱️ Compute time: {elapsed:.2f}s"
        self.send_response(200)
        for k, v in hdrs.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(text.encode("utf-8"))
