# api/overlap.py
import json, time, inspect
from http.server import BaseHTTPRequestHandler
from run_congestion import engine as _eng

NAME = "run-congestion overlap API"

# --- detect which kw the engine expects: step or step_km ---
_eng_sig = inspect.signature(_eng.analyze_overlaps)
if "step" in _eng_sig.parameters:
    _STEP_KW = "step"
elif "step_km" in _eng_sig.parameters:
    _STEP_KW = "step_km"
else:
    # extremely defensive: default to 'step'
    _STEP_KW = "step"

def _pick_step(payload):
    # Accept stepKm, step_km, or step; default 0.03
    if payload.get("stepKm") is not None:
        return float(payload["stepKm"])
    if payload.get("step_km") is not None:
        return float(payload["step_km"])
    if payload.get("step") is not None:
        return float(payload["step"])
    return 0.03

def _analyze_normalized(*, pace_csv, overlaps_csv, start_times, time_window, step_value, verbose, rank_by, segments):
    kwargs = dict(
        pace_csv=pace_csv,
        overlaps_csv=overlaps_csv,
        start_times=start_times,
        time_window=time_window,
        verbose=verbose,
        rank_by=rank_by,
        segments=segments,
    )
    kwargs[_STEP_KW] = step_value
    return _eng.analyze_overlaps(**kwargs)

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = {
            "ok": True,
            "name": NAME,
            "utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "engine_step_param": _STEP_KW,
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
            step_value = _pick_step(payload)
            verbose = bool(payload.get("verbose", False))
            rank_by = (payload.get("rankBy") or "peak_ratio")
            segments = payload.get("segments")

            if not pace_csv or not overlaps_csv or not start_times:
                raise ValueError("paceCsv, overlapsCsv, and startTimes are required")

            res = _analyze_normalized(
                pace_csv=pace_csv,
                overlaps_csv=overlaps_csv,
                start_times=start_times,
                time_window=time_window,
                step_value=step_value,
                verbose=verbose,
                rank_by=rank_by,
                segments=segments,
            )

            text = (res.get("text") or "").rstrip()
            eff = float(res.get("effective_step_km", step_value))
            footer = f"\n\nℹ️  Effective step used: {eff:.3f} km (requested {step_value:.3f} km)\n"
            out = (text + footer).encode("utf-8")

            dt = time.time() - t0
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=0, must-revalidate")
            self.send_header("X-Robots-Tag", "noindex")
            self.send_header("X-Request-UTC", time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()))
            self.send_header("X-Compute-Seconds", f"{dt:.2f}")
            self.send_header("X-StepKm", f"{eff:.3f}")
            self.send_header("X-Events-Seen", ",".join(sorted({*start_times.keys()})))
            self.end_headers()
            self.wfile.write(out)

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=0, must-revalidate")
            self.send_header("X-Robots-Tag", "noindex")
            self.end_headers()
            self.wfile.write(tb.encode("utf-8"))