# api/overlap.py
import json, time, traceback
from http.server import BaseHTTPRequestHandler
from run_congestion.engine_adapter import analyze_overlaps as _analyze

NAME = "run-congestion overlap API"

def _get_step_km(payload):
    # Accept any of these fields from the client; prefer stepKm
    if payload.get("stepKm") is not None:  # camelCase
        return float(payload["stepKm"])
    if payload.get("step_km") is not None:  # snake_case
        return float(payload["step_km"])
    if payload.get("step") is not None:     # legacy
        return float(payload["step"])
    return 0.03

class handler(BaseHTTPRequestHandler):
    # Health check
    def do_GET(self):
        body = {
            "ok": True,
            "name": NAME,
            "utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "commit": "",  # optionally fill via env if you like
            "python": "",
        }
        data = (json.dumps(body, ensure_ascii=False) + "%").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=0, must-revalidate")
        self.send_header("X-Robots-Tag", "noindex")
        self.end_headers()
        self.wfile.write(data)

    # Analyze
    def do_POST(self):
        t0 = time.time()
        try:
            n = int(self.headers.get("Content-Length") or "0")
            payload = json.loads(self.rfile.read(n) or b"{}")

            pace_csv     = payload.get("paceCsv")
            overlaps_csv = payload.get("overlapsCsv")
            start_times  = payload.get("startTimes") or {}
            time_window  = int(payload.get("timeWindow", 60))
            step_km      = _get_step_km(payload)
            verbose      = bool(payload.get("verbose", False))
            rank_by      = (payload.get("rankBy") or "peak_ratio")
            segments     = payload.get("segments")  # list like ["10K:5.81-8.10", ...]

            # Basic validation
            if not pace_csv or not overlaps_csv or not start_times:
                raise ValueError("paceCsv, overlapsCsv, and startTimes are required")

            # Call adapter (it will map to engine’s current signature)
            res = _analyze(
                pace_csv=pace_csv,
                overlaps_csv=overlaps_csv,
                start_times=start_times,
                time_window=time_window,
                step_km=step_km,
                verbose=verbose,
                rank_by=rank_by,
                segments=segments,
            )

            text = (res.get("text") or "").rstrip()
            effective = float(res.get("effective_step_km", step_km))

            footer = f"\n\nℹ️  Effective step used: {effective:.3f} km (requested {step_km:.3f} km)\n"
            if verbose and res.get("samples_per_segment"):
                # Pretty-print a small “samples per segment” block if provided
                lines = ["   Samples per segment (distance ticks):"]
                for label, count in res["samples_per_segment"]:
                    lines.append(f"   • {label}: {count} samples")
                footer += "\n".join(lines) + "\n"

            out = (text + footer).encode("utf-8")

            dt = time.time() - t0
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=0, must-revalidate")
            self.send_header("X-Robots-Tag", "noindex")
            self.send_header("X-Request-UTC", time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()))
            self.send_header("X-Compute-Seconds", f"{dt:.2f}")
            self.send_header("X-StepKm", f"{effective:.3f}")
            self.send_header("X-Events-Seen", ",".join(sorted(start_times.keys())))
            self.end_headers()
            self.wfile.write(out)

        except Exception as e:
            tb = traceback.format_exc()
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=0, must-revalidate")
            self.send_header("X-Robots-Tag", "noindex")
            self.end_headers()
            self.wfile.write(tb.encode("utf-8"))