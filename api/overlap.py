from __future__ import annotations

import json
import tempfile
from datetime import datetime, UTC
from http.server import BaseHTTPRequestHandler

import pandas as pd

# Stable adapter-backed entrypoint
from run_congestion.bridge import analyze_overlaps  # type: ignore


def _normalize_ov_df(df: pd.DataFrame) -> pd.DataFrame:
    ov = df.copy()
    for col in ("event", "overlapswith", "description"):
        if col in ov.columns:
            ov[col] = ov[col].astype(str).str.strip()
    ov["_event_norm"] = ov["event"].str.lower()
    return ov


def _parse_segments(tokens) -> list[dict]:
    out: list[dict] = []
    if not tokens:
        return out
    for tok in tokens:
        t = str(tok).strip()
        if ":" not in t or "-" not in t:
            raise ValueError(f"Invalid segment spec: '{t}'. Use Event:start-end (e.g., '10K:5.81-8.10').")
        ev, rng = t.split(":", 1)
        a, b = rng.split("-", 1)
        a, b = float(a), float(b)
        if b < a:
            a, b = b, a
        out.append({"event": ev.strip(), "event_norm": ev.strip().lower(), "start": a, "end": b})
    return out


def _filter_segments_or_message(ov_df: pd.DataFrame, segments):
    """Return (filtered_df, err_msg_or_None). If segments empty, returns (ov_df, None)."""
    if not segments:
        return ov_df, None

    ov = _normalize_ov_df(ov_df)
    req = _parse_segments(segments)

    valid_events = set(ov["_event_norm"].unique())
    keep_dfs = []
    mismatches = []

    # helper to format valid segments nicely
    def _all_valid_lines() -> list[str]:
        lines: list[str] = []
        for ev_name, g in ov.groupby("event"):
            g = g.sort_values(["start", "end"])
            for _, r in g.iterrows():
                lines.append(f"   - {ev_name}:{r.start:.2f}-{r.end:.2f} ({r.description})")
        return lines

    for seg in req:
        evn = seg["event_norm"]
        if evn not in valid_events:
            lines = _all_valid_lines()
            msg = f"• No such event in overlaps: {seg['event']}"
            if lines:
                msg += "\n  Valid segments:\n" + "\n".join(lines)
            mismatches.append(msg)
            continue

        rows = ov[(ov["_event_norm"] == evn) & (ov["start"] <= seg["end"]) & (ov["end"] >= seg["start"])]
        if rows.empty:
            g = ov[ov["_event_norm"] == evn].sort_values(["start", "end"])
            lines = [f"   - {g.iloc[0]['event']}:{r.start:.2f}-{r.end:.2f} ({r.description})" for _, r in g.iterrows()]
            msg = (
                f"• No overlapping range for {seg['event']} "
                f"({seg['start']:.2f}-{seg['end']:.2f})."
            )
            if lines:
                msg += "\n  Valid segments for this event:\n" + "\n".join(lines)
            mismatches.append(msg)
        else:
            keep_dfs.append(rows)

    if mismatches:
        req_list = "".join([f"- {s['event']}:{s['start']:.2f}-{s['end']:.2f}\n" for s in req])
        error = (
            "Your 'segments' request did not match one or more valid overlap segments.\n"
            "Requested segments:\n" + req_list + "\n" + "\n".join(mismatches)
        )
        return None, error

    filtered = pd.concat(keep_dfs, ignore_index=True).drop_duplicates(subset=["event", "start", "end", "overlapswith", "description"])
    # return only original columns
    cols = [c for c in ov_df.columns if c in ("event", "start", "end", "overlapswith", "description")]
    return filtered[cols], None


class handler(BaseHTTPRequestHandler):
    # Optional: reject GET for clarity
    def do_GET(self):
        self._send(405, "Use POST /api/overlap\n")

    def _send(self, code: int, body: str, content_type="text/plain; charset=utf-8", extra_headers: dict | None = None):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(n).decode("utf-8")
            data = json.loads(raw or "{}")
        except Exception as e:
            return self._send(400, f"Invalid JSON: {e}\n")

        # Required fields
        pace_csv = data.get("paceCsv")
        overlaps_csv = data.get("overlapsCsv")
        start_times = data.get("startTimes")
        if not pace_csv or not overlaps_csv or not start_times:
            return self._send(400, "'paceCsv', 'overlapsCsv', and 'startTimes' are required.\n")

        # Optional params
        time_window = int(data.get("timeWindow", 60))
        step_km = data.get("stepKm", data.get("step_km", data.get("step", 0.03)))
        try:
            step_km = float(step_km)
        except Exception:
            return self._send(400, "stepKm must be numeric.\n")
        verbose = bool(data.get("verbose", False))
        rank_by = data.get("rankBy", "peak_ratio")
        segments = data.get("segments")

        # Load overlaps (for validation & potential filtering)
        try:
            ov_df = pd.read_csv(overlaps_csv)
        except Exception as e:
            return self._send(400, f"Failed to read overlapsCsv: {e}\n")

        # Filter by segments, if requested
        filtered_path = None
        if segments:
            filtered, err = _filter_segments_or_message(ov_df, segments)
            if err:
                return self._send(400, err + "\n")
            # Persist to a temp CSV for the engine (it expects a path/URL)
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
            filtered.to_csv(tmp.name, index=False)
            filtered_path = tmp.name

        # Debug headers
        events_seen = ", ".join(sorted(ov_df["event"].astype(str).str.strip().unique()))
        hdrs = {
            "X-Request-UTC": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            "X-Events-Seen": events_seen,
            "X-StepKm": str(step_km),
        }

        try:
            # STRICTLY keyword args; no positional calls.
            result = analyze_overlaps(
                pace_csv=pace_csv,
                overlaps_csv=(filtered_path or overlaps_csv),
                start_times=start_times,
                time_window=time_window,
                step_km=step_km,
                verbose=verbose,
                rank_by=rank_by,
                segments=segments,
            )
        except Exception as e:
            # Return JSON error (easier to parse remotely)
            return self._send(500, json.dumps({"error": str(e)}) + "\n", content_type="application/json; charset=utf-8", extra_headers=hdrs)

        text = result.get("text") if isinstance(result, dict) else ""
        if not isinstance(text, str):
            text = str(text or "")

        return self._send(200, text, extra_headers=hdrs)
