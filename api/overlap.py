#!/usr/bin/env python3
# api/overlap.py
# Vercel-compatible handler: mirrors CLI footer with "Effective step used" and
# optional samples-per-segment when verbose=true.

import json
import sys
from datetime import datetime, timezone

# Prefer the adapter (adds meta & adapts step param); fallback to engine if missing.
try:
    from run_congestion.engine_adapter import analyze_overlaps
except Exception:
    from run_congestion.engine import analyze_overlaps  # type: ignore


def _parse_body(environ):
    try:
        length = int(environ.get("CONTENT_LENGTH") or "0")
    except ValueError:
        length = 0
    body = sys.stdin.read(length) if length > 0 else ""
    if not body.strip():
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {}

def _as_bool(v, default=False):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1","true","yes","y","on"): return True
        if s in ("0","false","no","n","off"): return False
    return default

def _start_response(status_code=200, headers=None):
    # Vercel Python runtime reads status line + headers from stdout
    # when using the "raw" handler pattern. If you are using a different
    # runtime wrapper, adapt accordingly.
    if headers is None:
        headers = {}
    print(f"Status: {status_code}", flush=False)
    for k, v in headers.items():
        print(f"{k}: {v}", flush=False)
    print("", flush=False)  # end of headers

def handler(environ, start_response=_start_response):
    payload = _parse_body(environ)

    pace_csv = payload.get("paceCsv") or payload.get("pace_csv")
    overlaps_csv = payload.get("overlapsCsv") or payload.get("overlaps_csv")
    start_times = payload.get("startTimes") or payload.get("start_times") or {}
    time_window = int(payload.get("timeWindow") or payload.get("time_window") or 60)
    # Accept both stepKm and step_km
    request_step = float(payload.get("stepKm", payload.get("step_km", 0.03)))
    verbose = _as_bool(payload.get("verbose"), False)
    rank_by = str(payload.get("rankBy", "peak_ratio"))
    segments = payload.get("segments")
    if segments is not None and not isinstance(segments, list):
        start_response(400, {"content-type": "text/plain; charset=utf-8"})
        print("Invalid 'segments': must be a list of strings like \"10K:5.81-8.10\".", flush=True)
        return

    # Call analysis (adapter ensures engine signature compatibility)
    try:
        res = analyze_overlaps(
            pace_csv=pace_csv,
            overlaps_csv=overlaps_csv,
            start_times=start_times,
            time_window=time_window,
            step_km=request_step,
            verbose=verbose,
            rank_by=rank_by,
            segments=segments,
        )
    except Exception as e:
        start_response(500, {"content-type": "text/plain; charset=utf-8"})
        print(f"Engine error: {e}", flush=True)
        return

    text = (res or {}).get("text", "") or ""
    meta = (res or {}).get("meta", {}) or {}
    effective = float(meta.get("effective_step_km", request_step))
    samples = meta.get("samples_per_segment") or {}

    # Build footer to mirror CLI
    lines = [text]
    lines.append("")
    lines.append(f"ℹ️  Effective step used: {effective:.3f} km (requested {request_step:.3f} km)")
    if verbose and samples:
        lines.append("   Samples per segment (distance ticks):")
        for seg, n in sorted(samples.items()):
            lines.append(f"   • {seg}: {n} samples")

    body = "\n".join(lines).strip() + "\n"

    headers = {
        "content-type": "text/plain; charset=utf-8",
        "x-stepkm": f"{effective:.3f}",
        "x-request-stepkm": f"{request_step:.3f}",
        "x-request-utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "x-robots-tag": "noindex",
        "cache-control": "public, max-age=0, must-revalidate",
    }
    start_response(200, headers)
    print(body, flush=True)


# Vercel entrypoint
def main():
    # Minimal CGI-like interface for Vercel Python builder.
    # The platform provides env with headers; stdin contains the body.
    # We'll pass os.environ to handler for body parsing.
    import os
    handler(os.environ, _start_response)

if __name__ == "__main__":
    main()
