#!/usr/bin/env python3
# api/overlap.py — robust Vercel handler
# - Uses engine_adapter.analyze_overlaps (signature-safe: step vs step_km)
# - Appends CLI-style footer: "Effective step used ...", and per-segment samples when verbose=true
# - Returns detailed error text on 500s to make debugging easy (instead of opaque FUNCTION_INVOCATION_FAILED)

import json
import traceback
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any, Dict, List, Optional

# Prefer the adapter (adds meta & adapts step param); fallback to engine if needed.
try:
    from run_congestion.engine_adapter import analyze_overlaps
except Exception:
    from run_congestion.engine import analyze_overlaps  # type: ignore


def _as_bool(v, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
            s = v.strip().lower()
            if s in ("1","true","yes","y","on"): return True
            if s in ("0","false","no","n","off"): return False
    return default


def _read_json_body(request) -> Dict[str, Any]:
    """
    Works across Vercel Python request objects (Werkzeug/Flask-like) and
    falls back to minimal parsing if get_json is not available.
    """
    # Flask/Werkzeug-style
    try:
        if hasattr(request, "get_json"):
            data = request.get_json(silent=True)
            if isinstance(data, dict):
                return data
    except Exception:
        pass

    # Try raw data
    try:
        if hasattr(request, "get_data"):
            raw = request.get_data(as_text=True)
        elif hasattr(request, "data"):
            raw = request.data.decode("utf-8") if isinstance(request.data, (bytes, bytearray)) else str(request.data)
        else:
            raw = ""
    except Exception:
        raw = ""

    if raw and raw.strip():
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {}


def _normalize_segments(v) -> Optional[List[str]]:
    if v is None:
        return None
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str):
        return [v]
    return None


def _footer_text(effective_step: float, requested_step: float, verbose: bool,
                 samples_per_segment: Optional[Dict[str, int]]) -> str:
    lines: List[str] = []
    lines.append("")
    lines.append(f"ℹ️  Effective step used: {effective_step:.3f} km (requested {requested_step:.3f} km)")
    if verbose and samples_per_segment:
        lines.append("   Samples per segment (distance ticks):")
        # Sort stably by event and numeric start
        def _k(k: str):
            try:
                ev, rng = k.split(":", 1)
                s, e = rng.split("-", 1)
                return (ev, float(s), float(e))
            except Exception:
                return (k, 0.0, 0.0)
        for key in sorted(samples_per_segment.keys(), key=_k):
            lines.append(f"   • {key}: {samples_per_segment[key]} samples")
    return "\n".join(lines)


def handler(request, response):
    """
    Vercel will pass (request, response) objects.
    We always return text/plain and append the CLI-style footer.
    On error we return 500 with the exception text to make triage easier.
    """
    try:
        payload = _read_json_body(request)

        pace_csv = payload.get("paceCsv") or payload.get("pace_csv")
        overlaps_csv = payload.get("overlapsCsv") or payload.get("overlaps_csv")
        start_times = payload.get("startTimes") or payload.get("start_times") or {}
        time_window = int(payload.get("timeWindow") or payload.get("time_window") or 60)
        # accept both stepKm / step_km
        requested_step = float(payload.get("stepKm", payload.get("step_km", 0.03)))
        verbose = _as_bool(payload.get("verbose"), False)
        rank_by = str(payload.get("rankBy", "peak_ratio"))
        segments = _normalize_segments(payload.get("segments"))

        if not pace_csv or not overlaps_csv:
            response.status_code = HTTPStatus.BAD_REQUEST
            response.headers["Content-Type"] = "text/plain; charset=utf-8"
            response.set_data("Missing required fields: paceCsv and overlapsCsv\n")
            return

        # Normalize start_times (dict is expected by engine)
        if isinstance(start_times, dict):
            st = {str(k): float(v) for k, v in start_times.items()}
        else:
            # Allow list of "Event=Minutes" strings
            st = {}
            for entry in start_times:
                if isinstance(entry, str) and "=" in entry:
                    k, v = entry.split("=", 1)
                    st[k].strip()  # ensure key exists
                    st[k.strip()] = float(v.strip())

        # Run analysis (adapter maps step_km to engine's parameter name)
        result = analyze_overlaps(
            pace_csv=pace_csv,
            overlaps_csv=overlaps_csv,
            start_times=st,
            time_window=time_window,
            step_km=requested_step,
            verbose=verbose,
            rank_by=rank_by,
            segments=segments,
        )

        text = str((result or {}).get("text", ""))
        meta = dict((result or {}).get("meta", {}))
        # engine_adapter sets effective_step_km; some engines used 'effective_step'
        effective = float(meta.get("effective_step_km", meta.get("effective_step", requested_step)))
        samples = meta.get("samples_per_segment") or {}

        # Append CLI-style footer
        text += _footer_text(effective, requested_step, verbose, samples)
        if not text.endswith("\n"):
            text += "\n"

        # Response
        response.status_code = HTTPStatus.OK
        response.headers["Content-Type"] = "text/plain; charset=utf-8"
        response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
        response.headers["X-Robots-Tag"] = "noindex"
        response.headers["X-StepKm"] = f"{effective:.3f}"
        response.headers["X-Request-StepKm"] = f"{requested_step:.3f}"
        response.headers["X-Request-UTC"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        response.set_data(text)

    except Exception as e:
        # Return detailed error text to avoid opaque FUNCTION_INVOCATION_FAILED
        response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        response.headers["Content-Type"] = "text/plain; charset=utf-8"
        tb = traceback.format_exc()
        response.set_data(f"Unhandled error in api/overlap.py:\n{e}\n\n{tb}")
