
#!/usr/bin/env python3
# api/overlap.py — WSGI-compatible handler for Vercel (Python)
# - Stateless (Hobby-tier friendly): no external storage
# - Optional segment filtering with friendly validation errors
# - Enforces stepKm >= 0.03 to avoid Hobby timeout risk; warns when clamped
# - Prepends timing block: request time, execution duration, response time
# - Returns the same terminal-style text as the CLI
#
# POST body JSON:
# {
#   "paceCsv": "https://.../your_pace_data.csv",
#   "overlapsCsv": "https://.../overlaps.csv",
#   "startTimes": {"Full": 420, "10K": 440, "Half": 460},
#   "timeWindow": 60,
#   "stepKm": 0.03,
#   "verbose": true,
#   "rankBy": "peak_ratio",
#   "segments": ["10K:5.81-8.10", {"event":"Full","start":29.03,"end":37.00}]
# }

import csv
import io
import json
import time
import urllib.request
from http import HTTPStatus
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Any

# Prefer a bridge shim if you have one; else import engine directly
try:
    from run_congestion.bridge import analyze_overlaps
except Exception:
    from run_congestion.engine import analyze_overlaps

MIN_STEP_KM = 0.03  # guardrail for Vercel Hobby timeout envelope

def _iso_utc(ts: float = None) -> str:
    dt = datetime.now(timezone.utc) if ts is None else datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def _read_json_body(environ) -> Dict[str, Any]:
    try:
        length = int(environ.get("CONTENT_LENGTH", "0"))
    except ValueError:
        length = 0
    body = environ.get("wsgi.input").read(length) if length > 0 else b""
    if not body:
        return {}
    return json.loads(body.decode("utf-8"))

def _resp(start_response, status: str, body: str, headers=None, content_type="text/plain; charset=utf-8"):
    hdrs = [("Content-Type", content_type)]
    if headers:
        hdrs.extend(headers)
    start_response(status, hdrs)
    return [body.encode("utf-8")]

def _fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={
        "Accept": "text/csv, text/plain;q=0.9, */*;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "User-Agent": "run-congestion/1.0"
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        # Python auto-decompresses gzip via urllib? Not guaranteed; try decode as utf-8 anyway.
        return raw.decode("utf-8", errors="replace")

def _parse_segments(spec) -> List[Tuple[str, float, float]]:
    out = []
    if not spec:
        return out
    for item in spec:
        if isinstance(item, str):
            s = item.replace("–", "-").strip()
            if ":" not in s or "-" not in s:
                raise ValueError(f"Invalid segment format: {item}. Expected 'Event:start-end'.")
            ev, rng = s.split(":", 1)
            a, b = rng.split("-", 1)
            out.append((ev.strip(), float(a), float(b)))
        elif isinstance(item, dict):
            ev = item.get("event")
            a = item.get("start")
            b = item.get("end")
            if ev is None or a is None or b is None:
                raise ValueError(f"Invalid segment object: {item}. Requires event,start,end.")
            out.append((str(ev).strip(), float(a), float(b)))
        else:
            raise ValueError(f"Unsupported segment entry: {item}")
    return out

def _load_overlaps_to_rows(overlaps_csv_url: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    txt = _fetch_text(overlaps_csv_url)
    f = io.StringIO(txt)
    reader = csv.DictReader(f)
    # normalize headers to lowercase
    fieldnames = [h.strip().lower() for h in reader.fieldnames or []]
    rows = []
    for raw in reader:
        row = {k.strip().lower(): v for k, v in raw.items()}
        # coerce numerics
        try:
            row["start"] = float(row.get("start", "0") or 0.0)
            row["end"] = float(row.get("end", "0") or 0.0)
        except Exception:
            pass
        rows.append(row)
    return rows, fieldnames

def _intersects(a1: float, a2: float, b1: float, b2: float) -> bool:
    lo1, hi1 = min(a1, a2), max(a1, a2)
    lo2, hi2 = min(b1, b2), max(b1, b2)
    return not (hi1 < lo2 or hi2 < lo1)

def _filter_overlaps(rows: List[Dict[str, Any]], wanted: List[Tuple[str, float, float]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Return (filtered_rows, errors). Errors contain friendly text for misses."""
    if not wanted:
        return rows, []
    errors = []
    filtered = []
    # Build index of valid ranges per event for error messaging
    by_event: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        ev = (r.get("event") or "").strip()
        by_event.setdefault(ev, []).append(r)

    for ev, a, b in wanted:
        ev_rows = by_event.get(ev)
        if not ev_rows:
            errors.append(f"• No such event in overlaps: {ev}")
            continue
        # Find any rows that intersect
        matches = [r for r in ev_rows if _intersects(a, b, float(r.get("start", 0)), float(r.get("end", 0)))]
        if not matches:
            # Prepare friendly list for this event
            lines = [f"• No overlapping range for {ev} ({a:.2f}-{b:.2f}). Valid segments for this event:"]
            for r in sorted(ev_rows, key=lambda x: float(x.get("start", 0))):
                desc = r.get("description") or r.get("desc") or ""
                lines.append(f"   - {ev}:{float(r.get('start',0)):.2f}-{float(r.get('end',0)):.2f} ({desc})")
            errors.append("\n".join(lines))
        else:
            filtered.extend(matches)
    # Deduplicate filtered (in case multiple wanted specs matched the same row)
    seen = set()
    unique = []
    for r in filtered:
        key = (r.get("event"), float(r.get("start",0)), float(r.get("end",0)), r.get("overlapswith"))
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique, errors

def _write_temp_overlaps(filtered_rows: List[Dict[str, Any]], fieldnames: List[str]) -> str:
    # Ensure standard columns exist
    base_fields = ["event", "start", "end", "overlapswith", "description"]
    fields = []
    for c in base_fields:
        if c in fieldnames:
            fields.append(c)
        else:
            fields.append(c)
    tmp_path = "/tmp/overlaps.filtered.csv"
    with open(tmp_path, "w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=base_fields)
        writer.writeheader()
        for r in filtered_rows:
            writer.writerow({
                "event": r.get("event",""),
                "start": r.get("start",""),
                "end": r.get("end",""),
                "overlapswith": r.get("overlapswith",""),
                "description": r.get("description") or r.get("desc") or ""
            })
    return tmp_path

def app(environ, start_response):
    if environ.get("REQUEST_METHOD") != "POST":
        return _resp(start_response, f"{HTTPStatus.METHOD_NOT_ALLOWED.value} {HTTPStatus.METHOD_NOT_ALLOWED.phrase}", "Use POST with JSON.")
    request_utc = _iso_utc()

    # Parse body
    try:
        req = _read_json_body(environ)
    except Exception as e:
        return _resp(start_response, f"{HTTPStatus.BAD_REQUEST.value} {HTTPStatus.BAD_REQUEST.phrase}", f"Invalid JSON: {e}", content_type="application/json; charset=utf-8")

    pace_csv = req.get("paceCsv")
    overlaps_csv = req.get("overlapsCsv")
    start_times = req.get("startTimes")
    if not pace_csv or not overlaps_csv or not start_times:
        return _resp(start_response, f"{HTTPStatus.BAD_REQUEST.value} {HTTPStatus.BAD_REQUEST.phrase}", "Missing required fields: paceCsv, overlapsCsv, startTimes", content_type="application/json; charset=utf-8")

    time_window = int(req.get("timeWindow", 60))
    step_km_req = float(req.get("stepKm", 0.03))
    step_km = step_km_req
    verbose = bool(req.get("verbose", True))
    rank_by = req.get("rankBy", "peak_ratio")
    segments_spec = req.get("segments", None)

    # Clamp & warn only if below the safe floor
    warning_lines = []
    if step_km < MIN_STEP_KM:
        warning_lines.append(f"⚠️ Requested stepKm={step_km:.3f} is below the API minimum ({MIN_STEP_KM:.2f}). Using {MIN_STEP_KM:.2f} to avoid timeout.")
        step_km = MIN_STEP_KM

    # Optional segment filtering
    filtered_overlaps_path = overlaps_csv
    if segments_spec:
        try:
            wanted = _parse_segments(segments_spec)
        except ValueError as ve:
            return _resp(start_response, f"{HTTPStatus.BAD_REQUEST.value} {HTTPStatus.BAD_REQUEST.phrase}", str(ve))
        try:
            rows, fields = _load_overlaps_to_rows(overlaps_csv)
        except Exception as e:
            return _resp(start_response, f"{HTTPStatus.BAD_REQUEST.value} {HTTPStatus.BAD_REQUEST.phrase}", f"Failed to load overlaps CSV: {e}")
        filtered_rows, errs = _filter_overlaps(rows, wanted)
        if errs:
            msg = ["Your 'segments' request did not match one or more valid overlap segments.","Requested segments:"]
            for ev,a,b in wanted:
                msg.append(f"- {ev}:{a:.2f}-{b:.2f}")
            msg.append("")
            msg.extend(errs)
            return _resp(start_response, f"{HTTPStatus.BAD_REQUEST.value} {HTTPStatus.BAD_REQUEST.phrase}", "\n".join(msg))
        if filtered_rows:
            filtered_overlaps_path = _write_temp_overlaps(filtered_rows, fields)

    # Execute analysis
    t0 = time.time()
    try:
        result = analyze_overlaps(
            pace_csv,
            filtered_overlaps_path,
            start_times,
            time_window=time_window,
            step_km=step_km,
            verbose=verbose,
            rank_by=rank_by
        )
    except Exception as e:
        return _resp(start_response, f"{HTTPStatus.INTERNAL_SERVER_ERROR.value} {HTTPStatus.INTERNAL_SERVER_ERROR.phrase}", json.dumps({"error": str(e)}), content_type="application/json; charset=utf-8")

    exec_ms = int((time.time() - t0) * 1000)
    response_utc = _iso_utc()

    # Normalize output (tuple or dict)
    if isinstance(result, tuple) and len(result) >= 2:
        report_text = result[0] or ""
    elif isinstance(result, dict):
        report_text = result.get("reportText", "") or result.get("text", "") or ""
    else:
        report_text = str(result) if result is not None else ""

    # Build timing banner
    timing_lines = []
    if warning_lines:
        timing_lines.extend(warning_lines)
    timing_lines.append(f"📅 Request received (UTC): {request_utc}")
    timing_lines.append(f"⏱️ Execution time: {exec_ms/1000.0:.3f} seconds")
    timing_lines.append(f"📤 Results returned (UTC): {response_utc}")
    timing_lines.append("")

    final_text = "\n".join(timing_lines) + report_text

    headers = [
        ("X-StepKm-Requested", f"{step_km_req}"),
        ("X-StepKm-Effective", f"{step_km}"),
        ("X-StepKm-Min", f"{MIN_STEP_KM}"),
        ("X-Exec-Ms", str(exec_ms)),
        ("X-Request-UTC", request_utc),
        ("X-Response-UTC", response_utc),
    ]
    return _resp(start_response, f"{HTTPStatus.OK.value} {HTTPStatus.OK.phrase}", final_text, headers=headers)
