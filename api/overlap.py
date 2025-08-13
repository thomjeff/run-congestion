# api/overlap.py
import json, time
from http.server import BaseHTTPRequestHandler
from run_congestion.engine_adapter import analyze_overlaps  # <-- use adapter

NAME = "run-congestion overlap API"

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = {
            "ok": True,
            "name": NAME,
            "utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        }
        out = (json.dumps(body, ensure_ascii=False) + "%").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=0, must-revalidate")
        self.send_header("X-Robots-Tag", "noindex")
        self.end_headers()
        self.wfile.write(out)

    def do_POST(self):
        t0 = time.time()
        try:
            n = int(self.headers.get("Content-Length") or "0")
            payload = json.loads(self.rfile.read(n) or b"{}")

            pace_csv = payload.get("paceCsv")
            overlaps_csv = payload.get("overlapsCsv")
            start_times = payload.get("startTimes") or {}
            time_window = int(payload.get("timeWindow", 60))
            step_km = float(payload.get("stepKm", 0.03))     # <-- API only accepts stepKm
            verbose = bool(payload.get("verbose", False))
            rank_by = (payload.get("rankBy") or "peak_ratio")
            segments = payload.get("segments")

            if not pace_csv or not overlaps_csv or not start_times:
                raise ValueError("paceCsv, overlapsCsv, and startTimes are required")

            res = analyze_overlaps(
                pace_csv=pace_csv,
                overlaps_csv=overlaps_csv,
                start_times=start_times,
                time_window=time_window,
                step_km=step_km,                 # <-- pass step_km only
                verbose=verbose,
                rank_by=rank_by,
                segments=segments,
            )

            text = (res.get("text") or "").rstrip()
            eff = float(res.get("effective_step_km", step_km))
            footer = f"\n\nℹ️  Effective step used: {eff:.3f} km (requested {step_km:.3f} km)\n"
            body = (text + footer).encode("utf-8")

            dt = time.time() - t0
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=0, must-revalidate")
            self.send_header("X-Robots-Tag", "noindex")
            self.send_header("X-Request-UTC", time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()))
            self.send_header("X-Compute-Seconds", f"{dt:.2f}")
            self.send_header("X-StepKm", f"{eff:.3f}")
            self.end_headers()
            self.wfile.write(body)

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=0, must-revalidate")
            self.send_header("X-Robots-Tag", "noindex")
            self.end_headers()
            self.wfile.write(tb.encode("utf-8"))