# api/overlap.py
# Vercel Python runtime handler (BaseHTTPRequestHandler) with robust error reporting.
# - GET: health JSON
# - POST: runs overlap analysis via run_congestion.engine_adapter (fallback to engine)
# - Adds headers: X-StepKm, X-Compute-Seconds, X-Events-Seen, X-Request-UTC
# - Returns CLI-like text; on error, returns full traceback in body.

from http.server import BaseHTTPRequestHandler
import json
import os
import time
import traceback
import datetime

def _to_bool(x, default=False):
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return bool(x)
    if isinstance(x, str):
        v = x.strip().lower()
        if v in ("1", "true", "yes", "y", "on"): return True
        if v in ("0", "false", "no", "n", "off"): return False
    return default

class handler(BaseHTTPRequestHandler):
    def _write(self, status=200, body="", headers=None, content_type="text/plain; charset=utf-8"):
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            if headers:
                for k, v in headers.items():
                    self.send_header(k, str(v))
            # Default caching like previous versions
            self.send_header("Cache-Control", "public, max-age=0, must-revalidate")
            self.end_headers()
            if isinstance(body, (bytes, bytearray)):
                self.wfile.write(body)
            else:
                self.wfile.write(str(body).encode("utf-8"))
        except Exception:
            # As a last resort, do nothing—connection may already be closed.
            pass

    def do_GET(self):
        info = {
            "ok": True,
            "name": "run-congestion overlap API",
            "utc": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "commit": os.environ.get("VERCEL_GIT_COMMIT_SHA", ""),
            "python": os.environ.get("PYTHON_VERSION", ""),
        }
        self._write(200, json.dumps(info), content_type="application/json; charset=utf-8")

    def do_POST(self):
        t0 = time.time()
        raw = b""
        try:
            length = int(self.headers.get("content-length", "0"))
            raw = self.rfile.read(length) if length > 0 else b""
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception as e:
            tb = traceback.format_exc()
            self._write(400, f"JSON parse error: {e}\n\n{tb}")
            return

        # Inputs
        paceCsv = data.get("paceCsv")
        overlapsCsv = data.get("overlapsCsv")
        startTimes = data.get("startTimes")
        timeWindow = data.get("timeWindow", 60)
        # Accept stepKm, step_km, step (in that order)
        stepKm = data.get("stepKm", data.get("step_km", data.get("step", 0.03)))
        rankBy = data.get("rankBy", "peak_ratio")
        verbose = _to_bool(data.get("verbose", False))
        segments = data.get("segments", None)

        if not paceCsv or not overlapsCsv or not startTimes:
            self._write(400, "Missing required fields: paceCsv, overlapsCsv, startTimes")
            return

        try:
            # Prefer adapter; fallback to engine
            try:
                from run_congestion.engine_adapter import analyze_overlaps as _analyze
            except Exception:
                from run_congestion.engine import analyze_overlaps as _analyze

            res = _analyze(
                pace_csv=paceCsv,
                overlaps_csv=overlapsCsv,
                start_times=startTimes,
                time_window=int(timeWindow),
                step=float(stepKm),
                verbose=verbose,
                rank_by=str(rankBy),
                segments=segments,
            )

            # Normalize output
            text_out = ""
            events_seen = None
            effective_step = None
            samples_per_segment = None

            if isinstance(res, dict):
                text_out = str(res.get("text") or res.get("body") or "")
                events_seen = res.get("events_seen")
                effective_step = res.get("effective_step")
                samples_per_segment = res.get("samples_per_segment")
            else:
                text_out = str(res)

            # Footer: Effective step + optional samples (to mirror CLI)
            requested = float(stepKm)
            eff = float(effective_step if effective_step is not None else requested)
            footer = [f"\nℹ️  Effective step used: {eff:.3f} km (requested {requested:.3f} km)"]
            if verbose and isinstance(samples_per_segment, dict) and samples_per_segment:
                footer.append("   Samples per segment (distance ticks):")
                for key, val in samples_per_segment.items():
                    footer.append(f"   • {key}: {val} samples")
            if footer:
                text_out = (text_out or "") + "\n" + "\n".join(footer)

            # Headers
            compute_secs = f"{time.time() - t0:.2f}"
            headers = {
                "X-Compute-Seconds": compute_secs,
                "X-Request-UTC": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "X-StepKm": f"{eff:.2f}",
            }
            if events_seen:
                if isinstance(events_seen, (list, tuple, set)):
                    headers["X-Events-Seen"] = ",".join(map(str, events_seen))
                else:
                    headers["X-Events-Seen"] = str(events_seen)

            self._write(200, text_out, headers=headers)

        except Exception as e:
            tb = traceback.format_exc()
            # Return full traceback so we can see the real cause
            self._write(500, tb)
