
import os
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Dict, Tuple

def parse_start_times(pairs):
    mapping = {}
    for p in pairs:
        if '=' not in p:
            raise ValueError(f"Invalid start time spec: {p}. Expected Format Event=minutes_since_midnight")
        event, val = p.split('=', 1)
        mapping[event.strip()] = float(val)
    return mapping

def time_str_from_minutes(minutes):
    total_seconds = int(round(minutes * 60))
    hours = total_seconds // 3600
    mins = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02d}:{mins:02d}:{secs:02d}"

def detect_segment_overlap(
    df: pd.DataFrame,
    prev_event: str,
    curr_event: str,
    start_prev_min: float,
    start_curr_min: float,
    seg_start_km: float,
    seg_end_km: float,
    time_window_secs: int = 60,
    step_km: float = 0.01,
    coarse_factor: int = 5
) -> Dict:
    # Filter by event
    prev_df = df[df['event'] == prev_event].copy().reset_index(drop=True)
    curr_df = df[df['event'] == curr_event].copy().reset_index(drop=True)
    if prev_df.empty or curr_df.empty:
        return None

    # Pre-filter based on arrival window endpoints
    prev_start = start_prev_min + prev_df['pace'] * seg_start_km
    prev_end   = start_prev_min + prev_df['pace'] * seg_end_km
    curr_start = start_curr_min + curr_df['pace'] * seg_start_km
    curr_end   = start_curr_min + curr_df['pace'] * seg_end_km

    prev_min = prev_start.values; prev_max = prev_end.values
    curr_min = curr_start.values; curr_max = curr_end.values

    window_mask = (prev_max[:, None] >= curr_min[None, :]) & (curr_max[None, :] >= prev_min[:, None])
    prev_keep = window_mask.any(axis=1)
    curr_keep = window_mask.any(axis=0)
    prev_df = prev_df.loc[prev_keep].reset_index(drop=True)
    curr_df = curr_df.loc[curr_keep].reset_index(drop=True)
    if prev_df.empty or curr_df.empty:
        return None

    # Coarse pass to identify candidate overlap windows
    coarse_step = step_km * coarse_factor
    coarse_steps = np.arange(seg_start_km, seg_end_km + 1e-9, coarse_step)

    prev_paces = prev_df['pace'].to_numpy()[:, None]
    curr_paces = curr_df['pace'].to_numpy()[:, None]
    prev_coarse = start_prev_min + prev_paces * coarse_steps
    curr_coarse = start_curr_min + curr_paces * coarse_steps

    candidate_kms = []
    for si, km in enumerate(coarse_steps):
        diff = np.abs(prev_coarse[:, si][:, None] - curr_coarse[:, si][None, :]) * 60
        if np.any(diff <= time_window_secs):
            candidate_kms.append(km)
    if not candidate_kms:
        return {
            'segment_start': seg_start_km,
            'segment_end': seg_end_km,
            'total_prev': len(prev_df),
            'total_curr': len(curr_df),
            'first_overlap': None,
            'cumulative_overlap_events': 0,
            'peak_congestion': 0,
            'peak_prev_at_peak': set(),
            'peak_curr_at_peak': set(),
            'unique_overlapping_pairs': 0
        }

    # Build refine ranges around each candidate km
    ranges = []
    for km in candidate_kms:
        low = max(seg_start_km, km - coarse_step)
        high = min(seg_end_km, km + coarse_step)
        ranges.append((low, high))
    ranges.sort()
    merged = [ranges[0]]
    for lo, hi in ranges[1:]:
        if lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))

    # Build refined steps list
    refined_steps = np.unique(np.concatenate([
        np.arange(lo, hi + 1e-9, step_km) for lo, hi in merged
    ]))

    # Vectorized arrival times on refined steps
    prev_arr = start_prev_min + prev_paces * refined_steps
    curr_arr = start_curr_min + curr_paces * refined_steps

    first_overlap = None
    cumulative_overlap_events = 0
    peak_congestion = 0
    peak_prev = set()
    peak_curr = set()
    unique_pairs = set()

    # Detailed scan on refined steps
    for si, km in enumerate(refined_steps):
        prev_times = prev_arr[:, si]
        curr_times = curr_arr[:, si]
        diff = np.abs(prev_times[:, None] - curr_times[None, :]) * 60
        hits = np.argwhere(diff <= time_window_secs)
        if hits.size:
            cumulative_overlap_events += hits.shape[0]
            for p_idx, c_idx in hits:
                unique_pairs.add((prev_df.iloc[p_idx]['runner_id'], curr_df.iloc[c_idx]['runner_id']))
            ev_times = np.minimum(prev_times[:, None], curr_times[None, :])[hits[:,0], hits[:,1]]
            idx = np.argmin(ev_times)
            p_hit, c_hit = hits[idx]
            event_time = ev_times[idx]
            if (first_overlap is None or event_time < first_overlap[0] or
                (abs(event_time - first_overlap[0]) < 1e-9 and km < first_overlap[1])):
                first_overlap = (event_time, km, prev_df.iloc[p_hit]['runner_id'], curr_df.iloc[c_hit]['runner_id'])
        if hits.size:
            prev_set = set(prev_df['runner_id'].iloc[hits[:,0]])
            curr_set = set(curr_df['runner_id'].iloc[hits[:,1]])
            total = len(prev_set) + len(curr_set)
            if total > peak_congestion:
                peak_congestion = total
                peak_prev = prev_set
                peak_curr = curr_set

    return {
        'segment_start': seg_start_km,
        'segment_end': seg_end_km,
        'total_prev': len(prev_df),
        'total_curr': len(curr_df),
        'first_overlap': first_overlap,
        'cumulative_overlap_events': cumulative_overlap_events,
        'peak_congestion': peak_congestion,
        'peak_prev_at_peak': peak_prev,
        'peak_curr_at_peak': peak_curr,
        'unique_overlapping_pairs': len(unique_pairs)
    }

def _process_segment(
    df: pd.DataFrame,
    prev_event: str,
    curr_event: str,
    start_prev: float,
    start_curr: float,
    seg_start: float,
    seg_end: float,
    desc: str,
    time_window: int,
    step_km: float,
    verbose: bool
) -> Tuple[List[str], Dict]:
    from run_congestion.engine import time_str_from_minutes  # ensure function available
    lines: List[str] = []
    label = f"{seg_start:.2f}km–{seg_end:.2f}km"
    if verbose:
        lines.append(f"🔍 Checking {prev_event} vs {curr_event} from {label}...")
        if desc:
            lines.append(f"📝 Segment: {desc}")
    res = detect_segment_overlap(df, prev_event, curr_event, start_prev, start_curr, seg_start, seg_end, time_window, step_km)
    if res is None:
        if verbose:
            lines.append(f"🟦 Overlap segment: {label}{' ('+desc+')' if desc else ''}")
            lines.append(f"👥 Total in '{curr_event}': 0 runners")
            lines.append(f"👥 Total in '{prev_event}': 0 runners")
            lines.append("✅ No overlap detected between events in this segment.")
            lines.append("")
        return lines, {}
    intensity = res['cumulative_overlap_events']
    seg_len = max(1e-9, seg_end - seg_start)
    intensity_per_km = intensity / seg_len
    peak_ratio = res['peak_congestion'] / (res['total_prev'] + res['total_curr'])
    record = {
        'prev_event': prev_event,
        'curr_event': curr_event,
        'segment': label,
        'description': desc,
        'intensity': intensity,
        'intensity_per_km': intensity_per_km,
        'distinct_pairs': res['unique_overlapping_pairs'],
        'peak_congestion': res['peak_congestion'],
        'peak_congestion_ratio': peak_ratio,
        'total_prev': res['total_prev'],
        'total_curr': res['total_curr'],
        'first_overlap_time': time_str_from_minutes(res['first_overlap'][0]) if res['first_overlap'] else '',
        'first_overlap_km': f"{res['first_overlap'][1]:.2f}" if res['first_overlap'] else ''
    }
    if verbose:
        lines.append(f"🟦 Overlap segment: {label}{' ('+desc+')' if desc else ''}")
        lines.append(f"👥 Total in '{curr_event}': {record['total_curr']} runners")
        lines.append(f"👥 Total in '{prev_event}': {record['total_prev']} runners")
        if record['first_overlap_time']:
            lines.append(f"⚠️ First overlap at {record['first_overlap_time']} at {record['first_overlap_km']}km -> {prev_event} Bib: {res['first_overlap'][2]}, {curr_event} Bib: {res['first_overlap'][3]}")
        else:
            lines.append("✅ No overlap detected between events in this segment.")
        lines.append(f"📈 Interaction Intensity over segment: {intensity:,} (cumulative overlap events)")
        lines.append(f"🔥 Peak congestion: {res['peak_congestion']} total runners at best step ({len(res['peak_prev_at_peak'])} from '{prev_event}', {len(res['peak_curr_at_peak'])} from '{curr_event}')")
        lines.append(f"🔁 Unique Pairs: {res['unique_overlapping_pairs']:,} (cross-bib relationships)")
        lines.append("")
    return lines, record
