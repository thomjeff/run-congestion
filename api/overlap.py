#!/usr/bin/env python3
# api/overlap.py  — WSGI-compatible, stateless handler for Vercel (Python)
# - No Blob/storage usage (Hobby-tier friendly)
# - Reads CSVs from URLs or paths, returns the same plain-text report as the CLI
# - Guards against Hobby timeouts by clamping stepKm >= 0.03
# - Supports both tuple and dict return shapes from analyze_overlaps

import json
import time
from http import HTTPStatus

# Prefer the bridge API if present; fall back to engine
try:
    from run_congestion.bridge import analyze_overlaps
except Exception:
    from run_congestion.engine import analyze_overlaps


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

    # Parse JSON payload
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

    # Parameters
    time_window = int(req.get("timeWindow", 60))
    step_km = float(req.get("stepKm", 0.03))
    verbose = bool(req.get("verbose", True))
    rank_by = req.get("rankBy", "peak_ratio")

    # Hobby guardrail
    if step_km < 0.03:
        step_km = 0.03

    t0 = time.time()
    try:
        # Signature compatible with your working engine/bridge
        result = analyze_overlaps(
            pace,
            overlaps,
            start_times,
            time_window=time_window,
            step_km=step_km,
            verbose=verbose,
            rank_by=rank_by,
        )
    except Exception as e:
        # Return structured failure for easier debugging
        payload = json.dumps({"error": str(e)}, ensure_ascii=False)
        return _resp(start_response, f"{HTTPStatus.INTERNAL_SERVER_ERROR.value} {HTTPStatus.INTERNAL_SERVER_ERROR.phrase}", payload, content_type="application/json; charset=utf-8")

    # Normalize return: tuple(text, summary) OR dict with 'reportText'
    if isinstance(result, tuple) and len(result) >= 2:
        report_text = result[0] or ""
    elif isinstance(result, dict):
        report_text = result.get("reportText", "") or ""
    else:
        report_text = str(result) if result is not None else ""

    headers = [("X-Compute-Ms", str(int((time.time() - t0) * 1000))), ("X-StepKm", str(step_km))]
    return _resp(start_response, f"{HTTPStatus.OK.value} {HTTPStatus.OK.phrase}", report_text, headers=headers)
