# api/overlap.py — WSGI handler with warm DF cache and segment scoping
import json
import os
import time
import tempfile
from http import HTTPStatus
from typing import List, Dict, Any

import pandas as pd

from run_congestion.io_cache import get_csv_df

# Prefer bridge; fall back to engine
try:
    from run_congestion.bridge import analyze_overlaps
except Exception:
    from run_congestion.engine import analyze_overlaps

TIMEOUT_STEP_LIMIT = 0.03  # Hobby guardrail: anything below this risks 300s timeout

def _read_json_body(environ):
    try:
        length = int(environ.get("CONTENT_LENGTH", "0"))
    except ValueError:
        length = 0
    body = environ.get("wsgi.input").read(length) if length > 0 else b""
    return json.loads(body.decode("utf-8")) if body else {}

def _resp(start_response, status: str, body: str, headers=None, content_type="text/plain; charset=utf-8"):
    hdrs = [("Content-Type", content_type)]
    if headers:
        hdrs.extend(headers)
    start_response(status, hdrs)
    return [body.encode("utf-8")]

def _parse_segments(spec: Any) -> List[Dict[str, Any]]:
    """Accept either strings 'Event:start-end' or dicts {event,start,end}.
    Returns normalized list of dicts. OverlapsWith is optional (filter by event & span only).
    """
    out = []
    if not spec:
        return out
    if isinstance(spec, list):
        for item in spec:
            if isinstance(item, str):
                # Example: '10K:5.81-8.10'
                try:
                    left, rng = item.split(":", 1)
                    s, e = rng.split("-", 1)
                    out.append({"event": left.strip(), "start": float(s), "end": float(e)})
                except Exception:
                    continue
            elif isinstance(item, dict):
                ev = item.get("event")
                st = item.get("start")
                en = item.get("end")
                ow = item.get("overlapsWith") or item.get("overlaps_with")
                if ev is not None and st is not None and en is not None:
                    out.append({"event": str(ev), "start": float(st), "end": float(en), "overlapsWith": (str(ow) if ow else None)})
    return out

def _filter_overlaps_df(overlaps_df: pd.DataFrame, segments: List[Dict[str, Any]]) -> pd.DataFrame:
    if not segments:
        return overlaps_df
    df = overlaps_df.copy()
    # Normalize columns
    cols = {c.lower(): c for c in df.columns}
    def col(name): return cols.get(name, name)
    if "event" not in cols or "start" not in cols or "end" not in cols:
        return overlaps_df  # schema mismatch; fail open

    mask_total = pd.Series(False, index=df.index)
    for seg in segments:
        m = (df[col("event")].astype(str) == seg["event"]) & (df[col("start")] >= seg["start"]) & (df[col("end")] <= seg["end"])
        if seg.get("overlapsWith"):
            if "overlapswith" in cols:
                m = m & (df[col("overlapswith")].astype(str) == seg["overlapsWith"])
            elif "overlaps_with" in cols:
                m = m & (df[col("overlaps_with")].astype(str) == seg["overlapsWith"])
        mask_total = mask_total | m
    filtered = df[mask_total]
    # If filter accidentally empty, keep original to avoid "no segments" surprise
    return filtered if not filtered.empty else overlaps_df

def app(environ, start_response):
    if environ.get("REQUEST_METHOD") != "POST":
        return _resp(start_response, f"{HTTPStatus.METHOD_NOT_ALLOWED.value} {HTTPStatus.METHOD_NOT_ALLOWED.phrase}", "Use POST with JSON.")

    try:
        req = _read_json_body(environ)
    except Exception as e:
        return _resp(start_response, f"{HTTPStatus.BAD_REQUEST.value} {HTTPStatus.BAD_REQUEST.phrase}", f"Invalid JSON: {e}", content_type="application/json; charset=utf-8")

    pace = req.get("paceCsv")
    overlaps = req.get("overlapsCsv")
    start_times = req.get("startTimes")
    if not pace or not overlaps or not start_times:
        return _resp(start_response, f"{HTTPStatus.BAD_REQUEST.value} {HTTPStatus.BAD_REQUEST.phrase}", "Missing required fields: paceCsv, overlapsCsv, startTimes", content_type="application/json; charset=utf-8")

    time_window = int(req.get("timeWindow", 60))
    requested_step = float(req.get("stepKm", TIMEOUT_STEP_LIMIT))
    verbose = bool(req.get("verbose", True))
    rank_by = req.get("rankBy", "peak_ratio")
    segments_spec = _parse_segments(req.get("segments"))

    # Clamp/warn only when below the safe limit
    eff_step = requested_step
    warning = None
    if eff_step < TIMEOUT_STEP_LIMIT:
        warning = f"⚠️ Requested stepKm={requested_step:.3f} is below the API's timeout-safe limit ({TIMEOUT_STEP_LIMIT:.2f}). Using {TIMEOUT_STEP_LIMIT:.2f} instead to avoid timeouts."
        eff_step = TIMEOUT_STEP_LIMIT

    # If a segment filter is provided, hydrate overlaps into DF, filter, write a temp CSV path
    overlaps_path = overlaps
    if segments_spec:
        try:
            ov_df = get_csv_df(overlaps)
            ov_f = _filter_overlaps_df(ov_df, segments_spec)
            # write to a temp file visible to runtime
            with tempfile.NamedTemporaryFile(mode="w+", suffix=".csv", delete=False) as tmp:
                ov_f.to_csv(tmp.name, index=False)
                overlaps_path = tmp.name
        except Exception as e:
            # fail open: proceed with original overlaps CSV
            overlaps_path = overlaps

    t0 = time.time()
    # Call your existing engine; pass URLs/paths directly
    result = analyze_overlaps(
        pace,
        overlaps_path,
        start_times,
        time_window=time_window,
        step_km=eff_step,
        verbose=verbose,
        rank_by=rank_by,
    )

    # Normalize return
    if isinstance(result, tuple) and len(result) >= 2:
        report_text = result[0] or ""
    elif isinstance(result, dict):
        report_text = result.get("reportText", "") or ""
    else:
        report_text = str(result) if result is not None else ""

    if warning:
        report_text = f"{warning}\n\n{report_text}"

    headers = [
        ("X-Compute-Ms", str(int((time.time() - t0) * 1000))),
        ("X-StepKm-Requested", str(requested_step)),
        ("X-StepKm-Effective", str(eff_step)),
        ("X-StepKm-Min", str(TIMEOUT_STEP_LIMIT)),
    ]
    return _resp(start_response, f"{HTTPStatus.OK.value} {HTTPStatus.OK.phrase}", report_text, headers=headers)
