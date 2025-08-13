#!/usr/bin/env python3
# api/overlap.py — aligned to your repo structure
# ✔ Imports: run_congestion.engine_adapter.analyze_overlaps (fallback to run_congestion.engine)
# ✔ Function: handler(request, response) — Vercel Python runtime entrypoint
# ✔ Footer: "Effective step used ..." + (verbose) samples-per-segment, same as CLI
# ✔ Errors: plain-text traceback in body (no more opaque FUNCTION_INVOCATION_FAILED)
# ✔ Health check: GET returns {"ok": true, ...}

from http import HTTPStatus
from typing import Any, Dict, List, Optional

def _as_bool(v, default: bool = False) -> bool:
    if isinstance(v, bool): return v
    if isinstance(v, (int, float)): return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1","true","yes","y","on"): return True
        if s in ("0","false","no","n","off"): return False
    return default

def _normalize_segments(v) -> Optional[List[str]]:
    if v is None: return None
    if isinstance(v, list): return [str(x) for x in v]
    if isinstance(v, str): return [v]
    return None

def _footer_text(effective_step: float, requested_step: float, verbose: bool,
                 samples_per_segment: Optional[Dict[str, int]]) -> str:
    lines: List[str] = []
    lines.append("")
    lines.append(f"ℹ️  Effective step used: {effective_step:.3f} km (requested {requested_step:.3f} km)")
    if verbose and samples_per_segment:
        lines.append("   Samples per segment (distance ticks):")
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
    import json, time, traceback
    from datetime import datetime, timezone

    # --- Health check (GET) ---
    if getattr(request, "method", "POST").upper() == "GET":
        response.status_code = HTTPStatus.OK
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        response.headers["Cache-Control"] = "no-store"
        response.set_data(json.dumps({
            "ok": True,
            "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        }))
        return

    t0 = time.perf_counter()
    request_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # --- Parse JSON body safely ---
    try:
        if hasattr(request, "get_json"):
            payload = request.get_json(silent=True) or {}
        else:
            raw = request.get_data(as_text=True) if hasattr(request, "get_data") else ""
            payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    try:
        # --- Defer heavy imports (so errors print to body) ---
        try:
            from run_congestion.engine_adapter import analyze_overlaps  # type: ignore
            adapter_used = True
        except Exception:
            from run_congestion.engine import analyze_overlaps  # type: ignore
            adapter_used = False

        # --- Inputs (support snake & camel case) ---
        pace_csv = payload.get("paceCsv") or payload.get("pace_csv")
        overlaps_csv = payload.get("overlapsCsv") or payload.get("overlaps_csv")
        start_times = payload.get("startTimes") or payload.get("start_times") or {}
        time_window = int(payload.get("timeWindow") or payload.get("time_window") or 60)
        requested_step = float(payload.get("stepKm", payload.get("step_km", 0.03)))
        verbose = _as_bool(payload.get("verbose"), False)
        rank_by = str(payload.get("rankBy", "peak_ratio"))
        segments = _normalize_segments(payload.get("segments"))

        if not pace_csv or not overlaps_csv:
            response.status_code = HTTPStatus.BAD_REQUEST
            response.headers["Content-Type"] = "text/plain; charset=utf-8"
            response.set_data("Missing required fields: paceCsv and overlapsCsv\n")
            return

        # Normalize start_times into dict[str,float]
        if isinstance(start_times, dict):
            st = {str(k): float(v) for k, v in start_times.items()}
        else:
            st = {}
            for entry in (start_times or []):
                if isinstance(entry, str) and "=" in entry:
                    k, v = entry.split("=", 1)
                    st[k.strip()] = float(v.strip())

        # --- Run analysis (adapter understands step_km) ---
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
        effective = float(meta.get("effective_step_km", meta.get("effective_step", requested_step)))
        samples = meta.get("samples_per_segment") or {}

        # --- Append CLI-style footer ---
        text += _footer_text(effective, requested_step, verbose, samples)
        if not text.endswith("\n"):
            text += "\n"

        # --- Respond ---
        elapsed = time.perf_counter() - t0
        response.status_code = HTTPStatus.OK
        response.headers["Content-Type"] = "text/plain; charset=utf-8"
        response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
        response.headers["X-Robots-Tag"] = "noindex"
        response.headers["X-StepKm"] = f"{effective:.3f}"
        response.headers["X-Request-StepKm"] = f"{requested_step:.3f}"
        response.headers["X-Request-UTC"] = request_utc
        response.headers["X-Compute-Seconds"] = f"{elapsed:.2f}"
        response.headers["X-Adapter-Used"] = "1" if adapter_used else "0"
        response.set_data(text)

    except Exception as e:
        # Surface full traceback in body for fast triage
        response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        response.headers["Content-Type"] = "text/plain; charset=utf-8"
        response.headers["Cache-Control"] = "no-store"
        import traceback
        response.set_data(f"Unhandled error in api/overlap.py:\n{e}\n\n{traceback.format_exc()}")
