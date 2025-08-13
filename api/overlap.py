#!/usr/bin/env python3
# api/overlap.py
# Ready-to-drop Vercel Python handler that appends the CLI-style footer:
#   "ℹ️  Effective step used: X.XXX km (requested Y.YYY km)"
# and (when verbose=true) prints samples-per-segment.
#
# It uses run_congestion.engine_adapter.analyze_overlaps to be compatible with
# engines that accept either `step` or `step_km`.

import json
import os
import sys
import time
from datetime import datetime, timezone

# Prefer the adapter; fall back to engine if needed.
try:
    from run_congestion.engine_adapter import analyze_overlaps
except Exception:
    from run_congestion.engine import analyze_overlaps  # type: ignore


def _parse_json_body(environ) -> dict:
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
    # Vercel’s Python runtime reads a status line and headers
    # terminated by a blank line, followed by the body.
    if headers is None:
        headers = {}
    print(f"Status: {status_code}")
    for k, v in headers.items():
        print(f"{k}: {v}")
    print("")  # end of headers


def handler(environ, start_response=_start_response):
    t0 = time.time()
    payload = _parse_json_body(environ)

    # Inputs (accept both camelCase and snake_case for robustness)
    pace_csv = payload.get("paceCsv") or payload.get("pace_csv")
    overlaps_csv = payload.get("overlapsCsv") or payload.get("overlaps_csv")
    start_times = payload.get("startTimes") or payload.get("start_times") or {}
    time_window = int(payload.get("timeWindow") or payload.get("time_window") or 60)
    request_step = float(payload.get("stepKm", payload.get("step_km", 0.03)))
    verbose = _as_bool(payload.get("verbose"), False)
    rank_by = str(payload.get("rankBy", "peak_ratio"))
    segments = payload.get("segments")
    if segments is not None and not isinstance(segments, list):
        start_response(400, {"content-type": "text/plain; charset=utf-8"})
        print('Invalid "segments": must be a list like ["10K:5.81-8.10", "Full:29.03-37.00"].')
        return

    # Call engine (adapter will map step param name and enrich meta)
    try:
        result = analyze_overlaps(
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
        print(f"Engine error: {e}")
        return

    elapsed = time.time() - t0

    # Assemble body with CLI-style footer
    text = (result or {}).get("text", "") or ""
    meta = (result or {}).get("meta", {}) or {}
    effective = float(meta.get("effective_step_km", request_step))
    samples = meta.get("samples_per_segment") or {}

    lines = [text, ""]
    lines.append(f"ℹ️  Effective step used: {effective:.3f} km (requested {request_step:.3f} km)")
    if verbose and samples:
        lines.append("   Samples per segment (distance ticks):")
        for seg, n in sorted(samples.items()):
            lines.append(f"   • {seg}: {n} samples")

    body = "\n".join(lines).rstrip() + "\n"

    headers = {
        "content-type": "text/plain; charset=utf-8",
        "cache-control": "public, max-age=0, must-revalidate",
        "x-stepkm": f"{effective:.3f}",
        "x-request-stepkm": f"{request_step:.3f}",
        "x-request-utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "x-compute-seconds": f"{elapsed:.2f}",
        "x-robots-tag": "noindex",
    }
    start_response(200, headers)
    print(body)


def main():
    handler(os.environ, _start_response)


if __name__ == "__main__":
    main()
