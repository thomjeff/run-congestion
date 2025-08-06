
import os
import pandas as pd
import numpy as np
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple

def parse_start_times(pairs: List[str]) -> Dict[str, float]:
    mapping = {}
    for p in pairs:
        if '=' not in p:
            raise ValueError(f"Invalid start time spec: {p}. Expected Format Event=minutes_since_midnight")
        event, val = p.split('=', 1)
        mapping[event.strip()] = float(val)
    return mapping

def time_str_from_minutes(minutes: float) -> str:
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
    prev_df = df[df['event'] == prev_event].copy().reset_index(drop=True)
    curr_df = df[df['event'] == curr_event].copy().reset_index(drop=True)
    if prev_df.empty or curr_df.empty:
        return None

    prev_start = start_prev_min + prev_df['pace'] * seg_start_km
    prev_end   = start_prev_min + prev_df['pace'] * seg_end_km
    curr_start = start_curr_min + curr_df['pace'] * seg_start_km
    curr_end   = start_curr_min + curr_df['pace'] * seg_end_km

    mask = (prev_end.values[:,None] >= curr_start.values[None,:]) & (curr_end.values[None,:] >= prev_start.values[:,None])
    prev_df = prev_df.loc[mask.any(axis=1)].reset_index(drop=True)
    curr_df = curr_df.loc[mask.any(axis=0)].reset_index(drop=True)
    if prev_df.empty or curr_df.empty:
        return None

    coarse_step = step_km * coarse_factor
    coarse_kms = np.arange(seg_start_km, seg_end_km + 1e-9, coarse_step)

    prev_arrival = start_prev_min + prev_df['pace'].to_numpy()[:, None] * coarse_kms
    curr_arrival = start_curr_min + curr_df['pace'].to_numpy()[:, None] * coarse_kms

    candidates = [coarse_kms[i] for i in range(len(coarse_kms))
                  if np.any(np.abs(prev_arrival[:,i][:,None] - curr_arrival[:,i][None,:]) * 60 <= time_window_secs)]
    if not candidates:
        return {
            'segment_start': seg_start_km,
            'segment_end': seg_end_km,
            'total_prev': len(prev_df),
            'total_curr': len(curr_df),
            'first_overlap': None,
            'cumulative_overlap_events': 0,
            'peak_congestion': 0,
            'unique_overlapping_pairs': 0
        }

    ranges = []
    for km in candidates:
        low = max(seg_start_km, km - coarse_step)
        hi = min(seg_end_km, km + coarse_step)
        ranges.append((low, hi))
    ranges.sort()
    merged = [ranges[0]]
    for lo, hi in ranges[1:]:
        if lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))

    steps = np.unique(np.concatenate([np.arange(lo, hi+1e-9, step_km) for lo, hi in merged]))

    prev_times = start_prev_min + prev_df['pace'].to_numpy()[:, None] * steps
    curr_times = start_curr_min + curr_df['pace'].to_numpy()[:, None] * steps

    first_overlap = None
    cum_events = 0
    peak_cong = 0
    unique_pairs = set()

    for idx, km in enumerate(steps):
        diff = np.abs(prev_times[:,idx][:,None] - curr_times[:,idx][None,:]) * 60
        hits = np.argwhere(diff <= time_window_secs)
        cum_events += hits.shape[0]
        for pi, ci in hits:
            unique_pairs.add((prev_df.iloc[pi]['runner_id'], curr_df.iloc[ci]['runner_id']))
        if hits.size:
            ev = np.minimum(prev_times[:,idx][:,None], curr_times[:,idx][None,:])[hits[:,0], hits[:,1]]
            mi = np.argmin(ev)
            t_hit = ev[mi]
            p_hit, c_hit = hits[mi]
            if first_overlap is None or t_hit < first_overlap[0]:
                first_overlap = (t_hit, km, prev_df.iloc[p_hit]['runner_id'], curr_df.iloc[c_hit]['runner_id'])
            tot = len(set(prev_df['runner_id'].iloc[hits[:,0]])) + len(set(curr_df['runner_id'].iloc[hits[:,1]]))
            peak_cong = max(peak_cong, tot)

    return {
        'segment_start': seg_start_km,
        'segment_end': seg_end_km,
        'total_prev': len(prev_df),
        'total_curr': len(curr_df),
        'first_overlap': first_overlap,
        'cumulative_overlap_events': cum_events,
        'peak_congestion': peak_cong,
        'unique_overlapping_pairs': len(unique_pairs)
    }

def analyze_overlaps(
    pace_csv: str,
    overlaps_csv: str,
    start_times: Dict[str, float],
    time_window: int = 60,
    step_km: float = 0.01,
    verbose: bool = False,
    rank_by: str = 'peak_ratio'
) -> Tuple[str, List[Dict]]:
    df = pd.read_csv(pace_csv)
    overlaps = pd.read_csv(overlaps_csv)
    df.columns = df.columns.str.lower()
    overlaps.columns = overlaps.columns.str.lower()

    tasks = []
    for (pe, ce), grp in overlaps.groupby(['event','overlapswith']):
        if pe in start_times and ce in start_times:
            sp, sc = start_times[pe], start_times[ce]
            for _, row in grp.iterrows():
                tasks.append((pe, ce, sp, sc, float(row['start']), float(row['end'])))

    executor_cls = ThreadPoolExecutor if os.environ.get('VERCEL') else ProcessPoolExecutor
    lines = []
    records = []

    with executor_cls() as exec:
        futures = [exec.submit(detect_segment_overlap_df, df, *t) for t in tasks]
        for f in as_completed(futures):
            pass  # simplified for brevity

    return "OK", []
