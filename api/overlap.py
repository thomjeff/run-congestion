#!/usr/bin/env python3
# api/overlap.py — WSGI-compatible, stateless handler for Vercel (Python)
# - Hobby-tier safe: no storage, no Blob
# - Returns terminal-style text; warns & clamps only when requested stepKm < 0.03
# - Adds telemetry headers for front-end awareness

import json
import time
from http import HTTPStatus

# Prefer bridge if available; fall back to engine
try:
    from run_congestion.bridge import analyze_overlaps
except Exception:
    from run_congestion.engine import analyze_overlaps


MIN_STEP_KM = 0.03  # API performance floor to avoid timeouts

def _read_json_body(environ):
    try:
        length = int(environ.get("CONTENT_LENGTH", "0"))
    except ValueError:
        length = 0
    body = environ.get("wsgi.input").read(length) if length > 0 else b""
    if not body:
        return {}
    try:
        return json.loads(body.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Invalid JSON: {e}")


def _resp(start_response, status: str, body: str, headers=None, content_type="text/plain; charset=utf-8"):
    hdrs = [("Content-Type", content_type)]
    if headers:
        hdrs.extend(headers)
    start_response(status, hdrs)
    return [body.encode("utf-8")]


def app(environ, start_response):
    if environ.get("REQUEST_METHOD") != "POST":
        return _resp(start_response, f"{HTTPStatus.METHOD_NOT_ALLOWED.value} {HTTPStatus.METHOD_NOT_ALLOWED.phrase}", "Use POST with JSON.")

    # Parse JSON
    try:
        req = _read_json_body(environ)
    except ValueError as e:
        return _resp(start_response, f"{HTTPStatus.BAD_REQUEST.value} {HTTPStatus.BAD_REQUEST.phrase}", str(e), content_type="application/json; charset=utf-8")

    pace = req.get("paceCsv")
    overlaps = req.get("overlapsCsv")
    start_times = req.get("startTimes")
    if not pace or not overlaps or not start_times:
        return _resp(
            start_response,
            f"{HTTPStatus.BAD_REQUEST.value} {HTTPStatus.BAD_REQUEST.phrase}",
            "Missing required fields: paceCsv, overlapsCsv, startTimes",
            content_type="application/json; charset=utf-8",
        )

    # Params
    time_window = int(req.get("timeWindow", 60))
    requested_step = float(req.get("stepKm", MIN_STEP_KM))
    verbose = bool(req.get("verbose", True))
    rank_by = req.get("rankBy", "peak_ratio")

    # Clamp only when requested < MIN_STEP_KM
    effective_step = requested_step
    warning_text = ""
    if requested_step < MIN_STEP_KM:
        effective_step = MIN_STEP_KM
        warning_text = (
            f"⚠️ Step clamp applied:\n"
            f"- Requested stepKm={requested_step:.3f} is below the API performance limit ({MIN_STEP_KM:.3f}).\n"
            f"- Using stepKm={effective_step:.3f} to avoid API timeouts.\n\n"
        )

    t0 = time.time()
    try:
        result = analyze_overlaps(
            pace,
            overlaps,
            start_times,
            time_window=time_window,
            step_km=effective_step,
            verbose=verbose,
            rank_by=rank_by,
        )
    except Exception as e:
        payload = json.dumps({"error": str(e)}, ensure_ascii=False)
        return _resp(start_response, f"{HTTPStatus.INTERNAL_SERVER_ERROR.value} {HTTPStatus.INTERNAL_SERVER_ERROR.phrase}", payload, content_type="application/json; charset=utf-8")

    # Normalize return
    if isinstance(result, tuple) and len(result) >= 2:
        report_text = result[0] or ""
    elif isinstance(result, dict):
        report_text = result.get("reportText", "") or ""
    else:
        report_text = str(result) if result is not None else ""

    if warning_text:
        report_text = warning_text + report_text

    headers = [
        ("X-Compute-Ms", str(int((time.time() - t0) * 1000))),
        ("X-StepKm-Requested", f"{requested_step:.3f}"),
        ("X-StepKm-Effective", f"{effective_step:.3f}"),
        ("X-StepKm-Min", f"{MIN_STEP_KM:.3f}"),
    ]
    return _resp(start_response, f"{HTTPStatus.OK.value} {HTTPStatus.OK.phrase}", report_text, headers=headers)
