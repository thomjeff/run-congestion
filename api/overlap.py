# api/overlap.py
import json
import time
import traceback
from http.server import BaseHTTPRequestHandler
from run_congestion import engine as _eng

NAME = "run-congestion overlap API"

def _pick_step(payload):
    # Accept stepKm, step_km, or step; default 0.03
    for k in ("stepKm", "step_km", "step"):
        if k in payload and payload[k] is not None:
            try:
                return float(payload[k])
            except Exception:
                pass
    return 0.03

def _engine_call_normalized(**kw):
    """Try engine with 'step' first, then with 'step_km' to tolerate either signature."""
    # First attempt: engines that accept 'step'
    try:
        return _eng.analyze_overlaps(
            pace_csv=kw["pace_csv"],
            overlaps_csv=kw["overlaps_csv"],
            start_times=kw["start_times"],
            time_window=kw["time_window"],
            step=kw["step"],
            verbose=kw["verbose"],
            rank_by=kw["rank_by"],
            segments=kw.get("segments"),
        )
    except TypeError:
        # Fallback: engines that accept 'step_km'
        return _eng.analyze_overlaps(
            pace_csv=kw["pace_csv"],
            overlaps_csv=kw["overlaps_csv"],
            start_times=kw["start_times"],
            time_window=kw["time_window"],
            step_km=kw["step"],
            verbose=kw["verbose"],
            rank_by=kw["rank_by"],
            segments=kw.get("segments"),
        )

class handler(BaseHTTPRequestHandler):
    def _json(self, code, obj, extra_headers=None):
        body = (json.dumps(obj, ensure_ascii=False) + "%").encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=0, must-revalidate")
        self.send_header("X-Robots-Tag", "noindex")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _text(self, code, text, extra_headers=None):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=0, must-revalidate")
        self.send_header("X-Robots-Tag", "noindex")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    # Health
    def do_GET(self):
        self._json(200, {
            "ok": True,
            "name": NAME,
            "utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "commit": "",  # Vercel won't know your git sha unless you inject it; leave blank
            "python": "",
        })

    # Analyze
    def do_POST(self):
        t0 = time.time()
        try:
            n = int(self.headers.get("Content-Length") or "0")
            payload = json.loads(self.rfile.read(n) or b"{}")
            pace_csv = payload.get("paceCsv")
            overlaps_csv = payload.get("overlapsCsv")
            start_times = payload.get("startTimes") or {}
            time_window = int(payload.get("timeWindow", 60))
            step = _pick_step(payload)
            verbose = bool(payload.get("verbose", False))
            rank_by = (payload.get("rankBy") or "peak_ratio")
            segments = payload.get("segments")

            if not pace_csv or not overlaps_csv or not start_times:
                raise ValueError("paceCsv, overlapsCsv, and startTimes are required")

            res = _engine_call_normalized(
                pace_csv=pace_csv,
                overlaps_csv=overlaps_csv,
                start_times=start_times,
                time_window=time_window,
                step=step,
                verbose=verbose,
                rank_by=rank_by,
                segments=segments,
            )

            text = (res.get("text") or "").rstrip()

            # Footer + headers parity
            eff = res.get("effective_step_km", step)
            footer_lines = [f"\n\nℹ️  Effective step used: {eff:.3f} km (requested {step:.3f} km)"]
            if verbose and "samples_per_segment" in res and isinstance(res["samples_per_segment"], dict):
                footer_lines.append("   Samples per segment (distance ticks):")
                for k, v in res["samples_per_segment"].items():
                    footer_lines.append(f"   • {k}: {v} samples")
            out = text + "\n".join(footer_lines) + "\n"

            dt = time.time() - t0
            self._text(200, out, extra_headers={
                "X-Request-UTC": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                "X-Compute-Seconds": f"{dt:.2f}",
                "X-StepKm": f"{eff:.3f}",
                "X-Events-Seen": ",".join(sorted({*start_times.keys()})),
            })

        except Exception as e:
            tb = traceback.format_exc()
            self._text(500, tb)