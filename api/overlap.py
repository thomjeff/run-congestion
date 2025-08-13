# api/overlap.py
from http.server import BaseHTTPRequestHandler
import json, time, traceback
from datetime import datetime, timezone

NAME = "run-congestion overlap API"

def _to_bool(x, default=False):
    if isinstance(x, bool): return x
    if isinstance(x, (int, float)): return bool(x)
    if isinstance(x, str):
        s = x.strip().lower()
        if s in ("1","true","yes","y","on"): return True
        if s in ("0","false","no","n","off"): return False
    return default

def _pick_step(payload):
    # Accept stepKm / step_km / step (in that preference)
    if payload.get("stepKm") is not None:     return float(payload["stepKm"])
    if payload.get("step_km") is not None:    return float(payload["step_km"])
    if payload.get("step") is not None:       return float(payload["step"])
    return 0.03

def _footer(effective_step, requested_step, verbose=False, samples=None):
    lines = []
    lines.append(f"\nℹ️  Effective step used: {effective_step:.3f} km (requested {requested_step:.3f} km)")
    if verbose and isinstance(samples, dict) and samples:
        lines.append("   Samples per segment (distance ticks):")
        for k in sorted(samples.keys()):
            lines.append(f"   • {k}: {samples[k]} samples")
    return "\n".join(lines)

def _analyze_normalized(**kw):
    """
    Try analyze_overlaps with step_km=..., then fall back to step=...
    This de-risks engine signature drift between local and Vercel builds.
    """
    # Prefer adapter (adds meta); fallback to engine
    try:
        from run_congestion.engine_adapter import analyze_overlaps as _analyze
    except Exception:
        from run_congestion.engine import analyze_overlaps as _analyze  # type: ignore

    # Try step_km first
    try:
        return _analyze(
            pace_csv=kw["pace_csv"],
            overlaps_csv=kw["overlaps_csv"],
            start_times=kw["start_times"],
            time_window=kw["time_window"],
            step_km=kw["step"],            # preferred
            verbose=kw["verbose"],
            rank_by=kw["rank_by"],
            segments=kw.get("segments"),
        )
    except TypeError:
        # Fall back to engines that still use 'step'
        return _analyze(
            pace_csv=kw["pace_csv"],
            overlaps_csv=kw["overlaps_csv"],
            start_times=kw["start_times"],
            time_window=kw["time_window"],
            step=kw["step"],               # fallback
            verbose=kw["verbose"],
            rank_by=kw["rank_by"],
            segments=kw.get("segments"),
        )

class handler(BaseHTTPRequestHandler):
    # Health check
    def do_GET(self):
        body = {
            "ok": True,
            "name": NAME,
            "utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=0, must-revalidate")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))

    # Analysis
    def do_POST(self):
        t0 = time.time()
        try:
            n = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(n) if n > 0 else b"{}"
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception as e:
            tb = traceback.format_exc()
            self._write_error(400, f"JSON parse error: {e}\n\n{tb}")
            return

        try:
            pace_csv     = payload.get("paceCsv")
            overlaps_csv = payload.get("overlapsCsv")
            start_times  = payload.get("startTimes") or {}
            time_window  = int(payload.get("timeWindow", 60))
            step         = _pick_step(payload)
            verbose      = _to_bool(payload.get("verbose", False))
            rank_by      = (payload.get("rankBy") or "peak_ratio")
            segments     = payload.get("segments")

            if not pace_csv or not overlaps_csv or not start_times:
                self._write_error(400, "Missing required fields: paceCsv, overlapsCsv, startTimes")
                return

            res = _analyze_normalized(
                pace_csv=pace_csv,
                overlaps_csv=overlaps_csv,
                start_times=start_times,
                time_window=time_window,
                step=step,
                verbose=verbose,
                rank_by=rank_by,
                segments=segments,
            )

            # Normalize result
            text = (res.get("text") or "").rstrip() if isinstance(res, dict) else str(res).rstrip()
            meta = res.get("meta", {}) if isinstance(res, dict) else {}
            effective = float(
                meta.get("effective_step_km",
                meta.get("effective_step", step))
            )
            samples = meta.get("samples_per_segment")

            # Footer
            text += _footer(effective, step, verbose, samples)

            # Respond
            dt = time.time() - t0
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=0, must-revalidate")
            self.send_header("X-Request-UTC", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
            self.send_header("X-Compute-Seconds", f"{dt:.2f}")
            self.send_header("X-StepKm", f"{effective:.3f}")
            self.end_headers()
            self.wfile.write((text + "\n").encode("utf-8"))

        except Exception as e:
            tb = traceback.format_exc()
            self._write_error(500, f"{e}\n\n{tb}")

    def _write_error(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=0, must-revalidate")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))