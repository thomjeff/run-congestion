# api/overlap.py
from __future__ import annotations
import json
import pandas as pd
from datetime import datetime, UTC
from http.server import BaseHTTPRequestHandler

# Adapter-backed entrypoint (stable args)
from run_congestion.bridge import analyze_overlaps  # type: ignore


def _normalize_events_df(ov_df: pd.DataFrame) -> pd.DataFrame:
    ov = ov_df.copy()
    for col in ("event", "overlapswith", "description"):
        if col in ov.columns:
            ov[col] = ov[col].astype(str).str.strip()
    ov["_event_norm"] = ov["event"].str.lower()
    return ov


def _parse_segments(tokens):
    out = []
    if not tokens:
        return out
    for t in tokens:
        t = str(t).strip()
        if ":" not in t or "-" not in t:
            raise ValueError(f"Invalid segment spec: '{t}'. Use Event:start-end")
        ev, rng = t.split(":", 1)
        a, b = rng.split("-", 1)
        a, b = float(a), float(b)
        if b < a:
            a, b = b, a
        out.append({"event": ev.strip(), "event_norm": ev.strip().lower(), "start": a, "end": b})
    return out


def _filter_segments_or_error(ov_df: pd.DataFrame, segments):
    ov = _normalize_events_df(ov_df)
    req = _parse_segments(segments)

    if not req:
        return ov_df, None  # no filtering requested

    valid_events = set(ov["_event_norm"].unique())
    mismatches = []
    keep = []

    for seg in req:
        evn = seg["event_norm"]
        if evn not in valid_events:
            # list all valid segments (pretty)
            lines = []
            for ev_name, g in ov.groupby("event"):
                g = g.sort_values(["start", "end"])
                for _, r in g.iterrows():
                    lines.append(f"   - {ev_name}:{r.start:.2f}-{r.end:.2f} ({r.description})")
            mismatches.append(f"• No such event in overlaps: {seg['event']}")
            if lines:
                mismatches.append("  Valid segments:\n" + "\n".join(lines))
            continue

        rows = ov[(ov["_event_norm"] == evn) &
                  (ov["start"] <= seg["end"]) &
                  (ov["end"] >= seg["start"])]
        if rows.empty:
            g = ov[ov["_event_norm"] == evn].sort_values(["start", "end"])
            lines = [f"   - {g.iloc[0]['event']}:{r.start:.2f}-{r.end:.2f} ({r.description})" for _, r in g.iterrows()]
            mismatches.append(
                f"• No overlapping range for {seg['event']} ({seg['start']:.2f}-{seg['end']:.2f})."
                + ("\n  Valid segments for this event:\n" + "\n".join(lines) if lines else "")
            )
        else:
            keep.append(rows)

    if mismatches:
        msg = (
            "Your 'segments' request did not match one or more valid overlap segments.\n"
            "Requested segments:\n" + "".join([f"- {s['event']}:{s['start']:.2f}-{s['end']:.2f}\n" for s in req]) +
            "\n" + "\n".join(mismatches)
        )
        return None, msg

    filtered = pd.concat(keep, ignore_index=True)
    # return only original columns in original casing
    cols = [c for c in ov_df.columns if c in ("event", "start", "end", "overlapswith", "description")]
    return filtered[cols], None


class handler(BaseHTTPRequestHandler):
    def _send_text(self, code: int, body: str, extra_headers: dict | None = None):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, code: int, obj: dict):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        # Parse JSON
        try:
            n = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(n).decode("utf-8")
            data = json.loads(raw or "{}")
        except Exception as e:
            return self._send_text(400, f"Invalid JSON: {e}")

        # Inputs
        pace_csv = data.get("paceCsv")
        overlaps_csv = data.get("overlapsCsv")
        start_times = data.get("startTimes") or {}
        time_window = int(data.get("timeWindow", 60))
        # canonicalize step name
        step_km = data.get("stepKm", data.get("step_km", data.get("step", 0.03)))
        try:
            step_km = float(step_km)
        except Exception:
            return self._send_text(400, "stepKm must be numeric")
        segments = data.get("segments")

        if not pace_csv or not overlaps_csv:
            return self._send_text(400, "paceCsv and overlapsCsv are required")

        # Load overlaps for validation/filtering only
        try:
            ov_df = pd.read_csv(overlaps_csv)
        except Exception as e:
            return self._send_text(400, f"Failed to read overlapsCsv: {e}")

        # Normalize and filter by segments (case-insensitive)
        filtered, err = _filter_segments_or_error(ov_df, segments)
        if err:
            return self._send_text(400, err)

        # Build headers to help you debug remotely
        events_seen = ",".join(sorted(ov_df["event"].astype(str).str.strip().unique()))
        hdrs = {
            "X-Request-UTC": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            "X-Events-Seen": events_seen,
            "X-StepKm": str(step_km),
        }

        # Run analysis (all keyword args — no positionals)
        try:
            result = analyze_overlaps(
                pace_csv=pace_csv,
                overlaps_csv=overlaps_csv if filtered is ov_df else filtered,  # adapter can handle a DataFrame path or file-like
                start_times=start_times,
                time_window=time_window,
                step_km=step_km,
                verbose=bool(data.get("verbose", False)),
                rank_by=data.get("rankBy", "peak_ratio"),
                segments=segments,  # harmless if already filtered
            )
        except Exception as e:
            return self._send_json(500, {"error": str(e)})

        text = result.get("text") or ""
        return self._send_text(200, text, extra_headers=hdrs)