# engine.py — v1.1.x-compatible shim with full analyzer
# Exposes: analyze_overlaps(pace_csv, overlaps_csv, start_times, time_window=60, step=0.03,
#                           verbose=False, rank_by="peak_ratio", segments=None)
# Returns: {"text": <str>, "summary_df": pandas.DataFrame, "exec_ms": float, "request_utc": str, "response_utc": str}

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union
from datetime import datetime, timezone

import numpy as np
import pandas as pd


# --------------------------- Utilities ---------------------------

def _now_utc_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return datetime.now(timezone.utc).strftime(fmt)

def _time_str_from_minutes(minutes: float) -> str:
    total_seconds = int(round(minutes * 60))
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def _fmt_int(n: int) -> str:
    return f"{n:,}"

def _fmt_float(x: float, digits: int = 2) -> str:
    return f"{x:.{digits}f}"


# --------------------------- Core overlap per-segment ---------------------------

@dataclass
class SegmentStats:
    event_a: str
    event_b: str
    start_km: float
    end_km: float
    description: str
    total_a: int
    total_b: int
    first_overlap: Optional[Tuple[float, float, Union[str,int], Union[str,int]]]  # (time_min, km, a_id, b_id)
    cumulative_events: int
    peak_congestion: int
    peak_a_count: int
    peak_b_count: int
    unique_pairs: int

    def peak_ratio(self) -> float:
        denom = self.total_a + self.total_b
        return (self.peak_congestion / denom) if denom > 0 else 0.0

    def length_km(self) -> float:
        return max(0.0, self.end_km - self.start_km)

def _detect_segment_overlap(
    a_df: pd.DataFrame, b_df: pd.DataFrame,
    start_a_min: float, start_b_min: float,
    seg_start_km: float, seg_end_km: float,
    time_window_secs: int, step_km: float
) -> Tuple[Optional[Tuple[float,float,Union[str,int],Union[str,int]]], int, int, int, int, int]:
    """
    Returns:
      (first_overlap), cumulative_overlap_events, peak_congestion, peak_a_count, peak_b_count, unique_pairs
    """
    if a_df.empty or b_df.empty:
        return None, 0, 0, 0, 0, 0

    steps = np.arange(seg_start_km, seg_end_km + 1e-12, step_km)  # include end
    # Pre-arrays
    a_ids = a_df["runner_id"].to_numpy()
    b_ids = b_df["runner_id"].to_numpy()
    a_pace = a_df["pace"].astype(float).to_numpy()  # minutes per km
    b_pace = b_df["pace"].astype(float).to_numpy()

    first_overlap: Optional[Tuple[float,float,Union[str,int],Union[str,int]]] = None
    cumulative = 0
    peak_cong = 0
    peak_a = 0
    peak_b = 0

    # Track unique pairs with a rolling bitset (avoid huge memory). We'll collect a set of tuples.
    seen_pairs = set()

    tol_min = time_window_secs / 60.0

    # Loop over steps (vectorized inside for pairwise comparisons)
    for km in steps:
        a_times = start_a_min + a_pace * km  # shape (Na,)
        b_times = start_b_min + b_pace * km  # shape (Nb,)

        # Pairwise difference matrix using broadcasting
        diff = np.abs(a_times[:, None] - b_times[None, :])  # shape (Na, Nb)
        mask = diff <= tol_min  # boolean matrix

        # counts
        if not mask.any():
            continue

        # unique pairs + cumulative
        a_idx, b_idx = np.where(mask)
        cumulative += a_idx.size

        # first overlap: earliest event_time, tiebreak by km
        # event_time = min(a_time, b_time) — compute per pair
        event_times = np.minimum(a_times[a_idx], b_times[b_idx])
        # find argmin
        min_pos = event_times.argmin()
        candidate_time = float(event_times[min_pos])
        candidate = (candidate_time, float(km), a_ids[a_idx[min_pos]], b_ids[b_idx[min_pos]])
        if first_overlap is None or (candidate_time < first_overlap[0]) or (abs(candidate_time - first_overlap[0]) < 1e-9 and km < first_overlap[1]):
            first_overlap = candidate

        # peak congestion: number of distinct runners in any overlap at this step
        a_distinct = np.unique(a_idx).size
        b_distinct = np.unique(b_idx).size
        total_here = a_distinct + b_distinct
        if total_here > peak_cong:
            peak_cong = total_here
            peak_a = a_distinct
            peak_b = b_distinct

        # update seen pairs
        # Use integers/strings as-is to reduce memory
        for i, j in zip(a_idx, b_idx):
            seen_pairs.add((a_ids[i], b_ids[j]))

    return first_overlap, cumulative, peak_cong, peak_a, peak_b, len(seen_pairs)


# --------------------------- Public API ---------------------------

def analyze_overlaps(
    pace_csv: Union[str, bytes, io.BytesIO],
    overlaps_csv: Union[str, bytes, io.BytesIO],
    start_times: Dict[str, float],
    time_window: int = 60,
    step_km: float = 0.03,
    verbose: bool = False,
    rank_by: str = "peak_ratio",
    segments: Optional[Sequence[str]] = None
) -> Dict[str, object]:
    """
    Main engine used by both CLI and API bridge.

    Arguments:
      - pace_csv: path or URL (pandas can read http/https), or file-like/bytes
      - overlaps_csv: path or URL, or file-like
      - start_times: mapping {EventName: minutes_since_midnight}
      - time_window: seconds tolerance for overlap (-– default 60s)
      - step: distance step in kilometers (e.g., 0.03)
      - verbose: print per-segment details
      - rank_by: "peak_ratio" or "intensity"
      - segments: optional list like ["10K:5.81-8.10", "Full:29.03-37.00"]

    Returns:
      dict with keys:
        - "text": printable summary (str)
        - "summary_df": pandas DataFrame of per-segment metrics
        - "exec_ms": float (milliseconds)
        - "request_utc": str
        - "response_utc": str
    """
    t0 = datetime.now(timezone.utc)

    # Load CSVs
    pace_df = pd.read_csv(pace_csv)
    ov_df = pd.read_csv(overlaps_csv)

    pace_df.columns = [c.strip().lower() for c in pace_df.columns]
    ov_df.columns = [c.strip().lower() for c in ov_df.columns]

    # validate
    need_pace = {"event", "runner_id", "pace"}
    if not need_pace.issubset(pace_df.columns):
        raise ValueError(f"Pace CSV missing columns: {sorted(need_pace - set(pace_df.columns))}")
    need_ov = {"event", "start", "end", "overlapswith"}
    if not need_ov.issubset(ov_df.columns):
        raise ValueError(f"Overlaps CSV missing columns: {sorted(need_ov - set(ov_df.columns))}")
    if "description" not in ov_df.columns:
        ov_df["description"] = ""

    # Normalize types
    pace_df["event"] = pace_df["event"].astype(str)
    pace_df["runner_id"] = pace_df["runner_id"].astype(str)
    pace_df["pace"] = pace_df["pace"].astype(float)

    ov_df["event"] = ov_df["event"].astype(str)
    ov_df["overlapswith"] = ov_df["overlapswith"].astype(str)
    ov_df["start"] = ov_df["start"].astype(float)
    ov_df["end"] = ov_df["end"].astype(float)
    ov_df["description"] = ov_df["description"].astype(str)

    # Optional segment filter
    if segments:
        wanted = []
        errors = []
        for spec in segments:
            try:
                ev, rng = spec.split(":", 1)
                a, b = rng.split("-", 1)
                s = float(a)
                e = float(b)
                wanted.append((ev.strip(), s, e))
            except Exception:
                errors.append(spec)
        if errors:
            raise ValueError(f"Invalid segment spec(s): {errors}")

        # Build filter
        def _match(row):
            for ev, s, e in wanted:
                if row["event"] == ev and abs(row["start"] - s) < 1e-9 and abs(row["end"] - e) < 1e-9:
                    return True
            return False

        filtered = ov_df[ov_df.apply(_match, axis=1)]
        if filtered.empty:
            # Prepare a friendly message listing valid segments per event
            msg_lines = ["Your 'segments' request did not match one or more valid overlap segments.", "Requested segments:"]
            for spec in segments:
                msg_lines.append(f"- {spec}")
            # per-event listing
            by_ev = {}
            for _, r in ov_df.iterrows():
                by_ev.setdefault(r["event"], []).append(f'   - {r["event"]}:{r["start"]:.2f}-{r["end"]:.2f} ({r["description"]})')
            msg_lines.append("")
            for ev, rows in by_ev.items():
                msg_lines.append(f"• Valid segments for {ev}:")
                msg_lines.extend(rows)
            text = "\n".join(msg_lines)
            return {
                "text": text,
                "summary_df": pd.DataFrame(),
                "exec_ms": (datetime.now(timezone.utc) - t0).total_seconds() * 1000.0,
                "request_utc": _now_utc_str(),
                "response_utc": _now_utc_str(),
            }
        ov_df = filtered

    # Compute per segment
    out_lines: List[str] = []
    stats_list: List[SegmentStats] = []

    # Work through rows in the existing CSV order
    for _, row in ov_df.iterrows():
        ev_a = row["event"]
        ev_b = row["overlapswith"]
        s_km = float(row["start"])
        e_km = float(row["end"])
        desc = row.get("description", "")

        # Runners
        a_all = pace_df[pace_df["event"] == ev_a]
        b_all = pace_df[pace_df["event"] == ev_b]

        # If any missing, compute 0s segment
        if ev_a not in start_times or ev_b not in start_times:
            continue
        start_a = float(start_times[ev_a])
        start_b = float(start_times[ev_b])

        first, cumulative, peak, peak_a, peak_b, uniq = _detect_segment_overlap(
            a_all, b_all, start_a, start_b, s_km, e_km, time_window, step
        )
        if verbose:
            out_lines.append(f"🔍 Checking {ev_a} vs {ev_b} from {s_km:.2f}km–{e_km:.2f}km...")
            if desc:
                out_lines.append(f"📝 Segment: {desc}")
            out_lines.append(f"🟦 Overlap segment: {s_km:.2f}km–{e_km:.2f}km ({desc})" if desc else f"🟦 Overlap segment: {s_km:.2f}km–{e_km:.2f}km")
            out_lines.append(f"👥 Total in '{ev_b}': {_fmt_int(len(b_all))} runners")
            out_lines.append(f"👥 Total in '{ev_a}': {_fmt_int(len(a_all))} runners")

        if first is None:
            if verbose:
                out_lines.append("✅ No overlap detected between events in this segment.")
                out_lines.append("📈 Interaction Intensity over segment: 0 (cumulative overlap events)")
                out_lines.append("🔥 Peak congestion: 0 total runners at best step")
                out_lines.append("🔁 Unique Pairs: 0")
                out_lines.append("")
            stats_list.append(SegmentStats(
                event_a=ev_a, event_b=ev_b, start_km=s_km, end_km=e_km, description=desc,
                total_a=len(a_all), total_b=len(b_all),
                first_overlap=None, cumulative_events=0, peak_congestion=0, peak_a_count=0, peak_b_count=0, unique_pairs=0
            ))
            continue

        t_min, km_at, a_id, b_id = first
        if verbose:
            out_lines.append(f"⚠️ First overlap at {_time_str_from_minutes(t_min)} at {km_at:.2f}km -> {ev_a} Bib: {a_id}, {ev_b} Bib: {b_id}")
            out_lines.append(f"📈 Interaction Intensity over segment: {_fmt_int(cumulative)} (cumulative overlap events)")
            out_lines.append(f"🔥 Peak congestion: {_fmt_int(peak)} total runners at best step ({peak_a} from '{ev_a}', {peak_b} from '{ev_b}')")
            out_lines.append(f"🔁 Unique Pairs: {_fmt_int(uniq)}")
            out_lines.append("")

        stats_list.append(SegmentStats(
            event_a=ev_a, event_b=ev_b, start_km=s_km, end_km=e_km, description=desc,
            total_a=len(a_all), total_b=len(b_all),
            first_overlap=first, cumulative_events=cumulative, peak_congestion=peak,
            peak_a_count=peak_a, peak_b_count=peak_b, unique_pairs=uniq
        ))

    # Build summary
    if rank_by not in {"peak_ratio", "intensity"}:
        rank_by = "peak_ratio"

    rows = []
    for st in stats_list:
        length = max(1e-9, st.length_km())
        peak_ratio = st.peak_ratio() * 100.0
        intensity_per_km = st.cumulative_events / length
        rows.append({
            "event_pair": f"{st.event_a} vs {st.event_b}",
            "start_km": st.start_km,
            "end_km": st.end_km,
            "description": st.description,
            "peak": st.peak_congestion,
            "peak_ratio": peak_ratio,
            "intensity": st.cumulative_events,
            "intensity_per_km": intensity_per_km,
            "distinct_pairs": st.unique_pairs,
        })
    summary_df = pd.DataFrame(rows)

    # Ranking
    if not summary_df.empty:
        if rank_by == "intensity":
            summary_df = summary_df.sort_values(["intensity", "peak"], ascending=[False, False])
        else:
            summary_df = summary_df.sort_values(["peak_ratio", "peak"], ascending=[False, False])

    # Pretty print the summary
    if not summary_df.empty:
        out_lines.append("🗂️ Interaction Intensity Summary — ranked by {}:".format(
            "peak congestion ratio (acute bottlenecks)" if rank_by != "intensity" else "cumulative overlap events"
        ))
        for i, r in enumerate(summary_df.itertuples(index=False), start=1):
            out_lines.append(f"{i:02d}. {r.event_pair} {r.start_km:.2f}km–{r.end_km:.2f}km ({r.description}): "
                             f"PeakRatio={r.peak_ratio:.2f}%, Peak={_fmt_int(r.peak)}, "
                             f"Intensity/km={_fmt_float(r.intensity_per_km, 1)}, "
                             f"Intensity={_fmt_int(int(r.intensity))}, DistinctPairs={_fmt_int(int(r.distinct_pairs))}")
    text = "\n".join(out_lines)

    t1 = datetime.now(timezone.utc)
    exec_ms = (t1 - t0).total_seconds() * 1000.0

    return {
        "text": text,
        "summary_df": summary_df,
        "exec_ms": exec_ms,
        "request_utc": _now_utc_str(),
        "response_utc": _now_utc_str(),
    }
