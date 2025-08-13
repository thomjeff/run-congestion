# api/overlap.py
import json
import time
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any, Dict, List, Optional

from run_congestion.engine_adapter import analyze_overlaps  # normalizes to engine.analyze_overlaps
from run_congestion.engine_adapter import parse_start_times  # if you expose it there; else inline

def _json_error(msg: str, status: int = 500) -> tuple[str, int, list[tuple[str, str]]]:
    body = json.dumps({"error": msg})
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("X-Robots-Tag", "noindex"),
        ("Cache-Control", "public, max-age=0, must-revalidate"),
    ]
    return body, status, headers

def _coerce_step(payload: Dict[str, Any]) -> float:
    # Accept both stepKm and step_km; fall back to 0.03 if missing
    if "stepKm" in payload and isinstance(payload["stepKm"], (int, float)):
        return float(payload["stepKm"])
    if "step_km" in payload and isinstance(payload["step_km"], (int, float)):
        return float(payload["step_km"])
    return 0.03

def _coerce_segments(payload: Dict[str, Any]) -> Optional[List[str]]:
    segs = payload.get("segments")
    if segs is None:
        return None
    # Ensure list[str]
    if isinstance(segs, list):
        return [str(s) for s in segs]
    # Allow single string
    if isinstance(segs, str):
        return [segs]
    return None

def _footer_text(effective_step: float, requested_step: float, verbose: bool,
                 samples_per_segment: Optional[Dict[str, int]]) -> str:
    lines = []
    lines.append("")
    lines.append(f"ℹ️  Effective step used: {effective_step:.3f} km (requested {requested_step:.3f} km)")
    if verbose and samples_per_segment:
        lines.append("   Samples per segment (distance ticks):")
        # stable order: sort by event then numeric start
        def _parse_key(k: str):
            # Keys look like "Event:start-end"
            try:
                event, rng = k.split(":", 1)
                s, e = rng.split("-", 1)
                return (event, float(s), float(e))
            except Exception:
                return (k, 0.0, 0.0)
        for key in sorted(samples_per_segment.keys(), key=_parse_key):
            lines.append(f"   • {key}: {samples_per_segment[key]} samples")
    return "\n".join(lines)

def handler(request, response):
    # Minimal WSGI-like shim expected by Vercel Python runtime
    try:
        t0 = time.perf_counter()
        request_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        raw = request.get_data(as_text=True)  # type: ignore[attr-defined]
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            body, status, headers = _json_error("Invalid JSON in request body", 500)
            response.status_code = status
            for k, v in headers:
                response.headers[k] = v
            response.set_data(body)
            return

        pace_csv = payload.get("paceCsv")
        overlaps_csv = payload.get("overlapsCsv")
        start_times = payload.get("startTimes", {})
        time_window = int(payload.get("timeWindow", 60))
        requested_step = _coerce_step(payload)
        rank_by = str(payload.get("rankBy", "peak_ratio"))
        verbose = bool(payload.get("verbose", False))
        segments = _coerce_segments(payload)

        if not pace_csv or not overlaps_csv:
            body, status, headers = _json_error("Missing required fields: paceCsv and overlapsCsv", 500)
            response.status_code = status
            for k, v in headers:
                response.headers[k] = v
            response.set_data(body)
            return

        # Normalize startTimes (accept dict already)
        if isinstance(start_times, dict):
            st = {str(k): float(v) for k, v in start_times.items()}
        else:
            # If sent as list of "Event=Minutes" strings (rare for API), parse similarly
            st = parse_start_times(start_times)  # type: ignore[arg-type]

        # Run analysis (adapter maps step_km -> engine's step)
        res = analyze_overlaps(
            pace_csv=pace_csv,
            overlaps_csv=overlaps_csv,
            start_times=st,
            time_window=time_window,
            step_km=requested_step,          # adapter supports step_km
            verbose=verbose,
            rank_by=rank_by,
            segments=segments,
        )

        # Expect engine/adapter to return:
        # {
        #   "text": "<pretty output>",
        #   "meta": {
        #       "effective_step": float,
        #       "samples_per_segment": { "Event:start-end": int, ... }
        #   }
        # }
        txt = str(res.get("text", ""))
        meta = dict(res.get("meta", {}))
        effective_step = float(meta.get("effective_step", requested_step))
        samples_per_segment = meta.get("samples_per_segment")

        # Append footer (always include effective step; include samples when verbose)
        txt += _footer_text(effective_step, requested_step, verbose, samples_per_segment)

        compute_s = time.perf_counter() - t0

        # Write response
        response.status_code = HTTPStatus.OK
        response.headers["Content-Type"] = "text/plain; charset=utf-8"
        response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
        response.headers["X-Robots-Tag"] = "noindex"

        # Useful diagnostics
        response.headers["X-Request-UTC"] = request_utc
        response.headers["X-Compute-Seconds"] = f"{compute_s:.2f}"
        # Show the **effective** step used (not just requested)
        response.headers["X-StepKm"] = f"{effective_step:.2f}"
        # A quick sanity header of which events were seen (best-effort)
        try:
            # This mirrors what your current route prints
            # (we don't re-parse CSVs here—just pass through if engine provided it)
            events_seen = res.get("events_seen")
            if isinstance(events_seen, list):
                response.headers["X-Events-Seen"] = ",".join(events_seen)
        except Exception:
            pass

        response.set_data(txt)

    except Exception as e:
        body, status, headers = _json_error(str(e), 500)
        response.status_code = status
        for k, v in headers:
            response.headers[k] = v
        response.set_data(body)