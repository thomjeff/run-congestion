#!/usr/bin/env python3
# api/overlap.py — WSGI handler (Hobby-tier safe)
# - Reads CSVs (URLs/paths)
# - Optional `segments` filter; validates against overlaps.csv and errors with friendly message if no match
# - Clamps stepKm < 0.03 to 0.03 with a visible warning
# - Returns terminal-style text; adds step headers

import json
import io
import time
from http import HTTPStatus
from typing import List, Dict, Tuple, Any

import pandas as pd

try:
    from run_congestion.bridge import analyze_overlaps
except Exception:
    from run_congestion.engine import analyze_overlaps

MIN_STEP_KM = 0.03

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

def _parse_segment_item(item: Any) -> Tuple[str, float, float]:
    """Accepts '10K:5.81-8.10' (hyphen or en-dash) or {'event':..., 'start':..., 'end':...}."""
    if isinstance(item, dict):
        ev = str(item.get("event", "")).strip()
        st = float(item.get("start"))
        en = float(item.get("end"))
        return ev, min(st, en), max(st, en)
    if isinstance(item, str):
        s = item.strip()
        s = s.replace("–", "-")  # normalize en dash
        if ":" not in s or "-" not in s:
            raise ValueError(f"Invalid segment format: {item!r}. Use 'Event:start-end' or object with event/start/end.")
        ev, rng = s.split(":", 1)
        st_s, en_s = rng.split("-", 1)
        st = float(st_s)
        en = float(en_s)
        return ev.strip(), min(st, en), max(st, en)
    raise ValueError(f"Unsupported segment entry: {item!r}")

def _normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    # normalize expected columns
    rename_map = {}
    if "overlapswith" not in df.columns and "overlaps_with" in df.columns:
        rename_map["overlaps_with"] = "overlapswith"
    if rename_map:
        df = df.rename(columns=rename_map)
    return df

def _load_overlaps_df(overlaps_src: str) -> pd.DataFrame:
    df = pd.read_csv(overlaps_src)
    return _normalize_cols(df)

def _filter_overlaps(df: pd.DataFrame, requested: List[Tuple[str, float, float]]) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """Return filtered overlaps, and a list of unmatched requested items with suggestions."""
    out_rows = []
    unmatched = []
    # build quick index by event (case-insensitive)
    df_event_norm = df["event"].astype(str).str.strip()
    df = df.assign(_event_norm=df_event_norm.str.lower())
    event_to_rows = {ev: grp.copy() for ev, grp in df.groupby("_event_norm")}

    for ev, st, en in requested:
        ev_norm = ev.strip().lower()
        group = event_to_rows.get(ev_norm)
        if group is None or group.empty:
            # No such event; suggest available events
            suggestions = sorted(set(df["_event_norm"].str.upper().tolist()))
            unmatched.append({"event": ev, "start": st, "end": en, "reason": "event_not_found", "available_events": suggestions})
            continue
        # ranges that intersect with [st,en]
        mask = (group["start"] <= en + 1e-9) & (group["end"] >= st - 1e-9)
        subset = group.loc[mask]
        if subset.empty:
            # build valid ranges for this event
            vals = [
                {
                    "event": str(r["event"]),
                    "start": float(r["start"]),
                    "end": float(r["end"]),
                    "description": str(r.get("description", "")),
                }
                for _, r in group.iterrows()
            ]
            unmatched.append({"event": ev, "start": st, "end": en, "reason": "range_not_found", "valid_segments": vals})
            continue
        out_rows.append(subset.drop(columns=["_event_norm"]))

    if out_rows:
        filtered = pd.concat(out_rows, ignore_index=True)
        # de-dup exact duplicate rows if any
        filtered = filtered.drop_duplicates(subset=["event", "start", "end", "overlapswith", "description"], keep="first")
    else:
        filtered = pd.DataFrame(columns=list(df.drop(columns=["_event_norm"]).columns))
    return filtered, unmatched

def app(environ, start_response):
    if environ.get("REQUEST_METHOD") != "POST":
        return _resp(start_response, f"{HTTPStatus.METHOD_NOT_ALLOWED.value} {HTTPStatus.METHOD_NOT_ALLOWED.phrase}", "Use POST with JSON.")

    try:
        req = _read_json_body(environ)
    except Exception as e:
        return _resp(start_response, f"{HTTPStatus.BAD_REQUEST.value} {HTTPStatus.BAD_REQUEST.phrase}", f"Invalid JSON: {e}", content_type="application/json; charset=utf-8")

    pace_src = req.get("paceCsv") or req.get("pace")
    overlaps_src = req.get("overlapsCsv") or req.get("overlaps")
    start_times = req.get("startTimes")
    if not pace_src or not overlaps_src or not start_times:
        return _resp(start_response, f"{HTTPStatus.BAD_REQUEST.value} {HTTPStatus.BAD_REQUEST.phrase}", "Missing required fields: paceCsv, overlapsCsv, startTimes", content_type="application/json; charset=utf-8")

    time_window = int(req.get("timeWindow", 60))
    step_km_req = float(req.get("stepKm", 0.03))
    rank_by = req.get("rankBy", "peak_ratio")
    verbose = bool(req.get("verbose", True))

    # Guardrail clamp
    step_km = step_km_req
    warning_lines = []
    if step_km < MIN_STEP_KM:
        warning_lines.append(f"⚠️ Step clamp applied:\n- Requested stepKm={step_km:.3f} is below the API performance limit ({MIN_STEP_KM:.3f}).\n- Using stepKm={MIN_STEP_KM:.3f} to avoid API timeouts.")
        step_km = MIN_STEP_KM

    # Segment filtering (optional)
    segments = req.get("segments")
    overlaps_path_for_engine = overlaps_src
    if segments:
        # parse requested
        try:
            requested = [_parse_segment_item(item) for item in segments]
        except Exception as e:
            return _resp(start_response, f"{HTTPStatus.BAD_REQUEST.value} {HTTPStatus.BAD_REQUEST.phrase}", f"Invalid segments: {e}", content_type="application/json; charset=utf-8")
        try:
            ov_df = _load_overlaps_df(overlaps_src)
        except Exception as e:
            return _resp(start_response, f"{HTTPStatus.BAD_REQUEST.value} {HTTPStatus.BAD_REQUEST.phrase}", f"Failed to load overlaps CSV: {e}", content_type="application/json; charset=utf-8")
        filtered_df, unmatched = _filter_overlaps(ov_df, requested)
        if unmatched:
            # Build friendly message echoing what user sent, and offering valid options per event
            lines = ["Your 'segments' request did not match one or more valid overlap segments.", "Requested segments:"]
            for ev, st, en in requested:
                lines.append(f"- {ev}:{st:.2f}-{en:.2f}")
            lines.append("")
            # Group unmatched by reason
            for item in unmatched:
                if item["reason"] == "event_not_found":
                    lines.append(f"• Event not found: {item['event']} (requested {item['start']:.2f}-{item['end']:.2f}). Available events: {', '.join(item['available_events']) or '—'}")
                elif item["reason"] == "range_not_found":
                    lines.append(f"• No overlapping range for {item['event']} ({item['start']:.2f}-{item['end']:.2f}). Valid segments for this event:")
                    for seg in item["valid_segments"]:
                        desc = f" ({seg['description']})" if seg.get("description") else ""
                        lines.append(f"   - {seg['event']}:{seg['start']:.2f}-{seg['end']:.2f}{desc}")
            msg = "\n".join(lines)
            return _resp(start_response, f"{HTTPStatus.BAD_REQUEST.value} {HTTPStatus.BAD_REQUEST.phrase}", msg, content_type="text/plain; charset=utf-8")
        # If we get here, all requested segments matched at least one row
        if filtered_df.empty:
            return _resp(start_response, f"{HTTPStatus.BAD_REQUEST.value} {HTTPStatus.BAD_REQUEST.phrase}", "No segments remained after filtering; please check your request.", content_type="text/plain; charset=utf-8")
        # Write to a temp CSV in /tmp (writable in serverless) and pass that to engine
        tmp_path = "/tmp/overlaps.filtered.csv"
        filtered_df.to_csv(tmp_path, index=False)
        overlaps_path_for_engine = tmp_path

    t0 = time.time()
    try:
        result = analyze_overlaps(
            pace_src,
            overlaps_path_for_engine,
            start_times,
            time_window=time_window,
            step_km=step_km,
            verbose=verbose,
            rank_by=rank_by,
        )
    except Exception as e:
        payload = json.dumps({"error": str(e)}, ensure_ascii=False)
        return _resp(start_response, f"{HTTPStatus.INTERNAL_SERVER_ERROR.value} {HTTPStatus.INTERNAL_SERVER_ERROR.phrase}", payload, content_type="application/json; charset=utf-8")

    # Normalize result
    if isinstance(result, tuple) and len(result) >= 2:
        report_text = result[0] or ""
    elif isinstance(result, dict):
        report_text = result.get("reportText", "") or ""
    else:
        report_text = str(result) if result is not None else ""

    if warning_lines:
        report_text = "\n".join(warning_lines) + "\n\n" + report_text

    headers = [
        ("X-StepKm-Requested", f"{step_km_req}"),
        ("X-StepKm-Effective", f"{step_km}"),
        ("X-StepKm-Min", f"{MIN_STEP_KM}"),
        ("X-Compute-Ms", str(int((time.time() - t0) * 1000))),
    ]

    return _resp(start_response, f"{HTTPStatus.OK.value} {HTTPStatus.OK.phrase}", report_text, headers=headers)
