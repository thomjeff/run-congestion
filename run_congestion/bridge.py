import os
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed

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

def _detect_segment_overlap(
    df: pd.DataFrame,
    prev_event: str, curr_event: str,
    start_prev_min: float, start_curr_min: float,
    seg_start_km: float, seg_end_km: float,
    time_window_secs: int = 60, step_km: float = 0.01, coarse_factor: int = 5
) -> Dict:
    prev_df = df[df['event'] == prev_event].copy().reset_index(drop=True)
    curr_df = df[df['event'] == curr_event].copy().reset_index(drop=True)
    if prev_df.empty or curr_df.empty:
        return None

    prev_start = start_prev_min + prev_df['pace'] * seg_start_km
    prev_end   = start_prev_min + prev_df['pace'] * seg_end_km
    curr_start = start_curr_min + curr_df['pace'] * seg_start_km
    curr_end   = start_curr_min + curr_df['pace'] * seg_end_km

    mask = ((prev_end.values[:,None] >= curr_start.values[None,:]) &
            (curr_end.values[None,:] >= prev_start.values[:,None]))
    prev_df = prev_df.loc[mask.any(axis=1)].reset_index(drop=True)
    curr_df = curr_df.loc[mask.any(axis=0)].reset_index(drop=True)
    if prev_df.empty or curr_df.empty:
        return None

    coarse_step = step_km * coarse_factor
    coarse_kms = np.arange(seg_start_km, seg_end_km + 1e-9, coarse_step)
    prev_paces = prev_df['pace'].to_numpy()[:, None]
    curr_paces = curr_df['pace'].to_numpy()[:, None]
    prev_coarse = start_prev_min + prev_paces * coarse_kms
    curr_coarse = start_curr_min + curr_paces * coarse_kms

    candidates = [km for i, km in enumerate(coarse_kms)
                  if np.any(np.abs(prev_coarse[:,i][:,None] - curr_coarse[:,i][None,:]) * 60 <= time_window_secs)]
    if not candidates:
        return {
            'segment_start': seg_start_km, 'segment_end': seg_end_km,
            'total_prev': len(prev_df), 'total_curr': len(curr_df),
            'first_overlap': None, 'cumulative_overlap_events': 0,
            'peak_congestion': 0, 'unique_overlapping_pairs': 0
        }

    ranges = []
    for km in candidates:
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

    refined = np.unique(np.concatenate([np.arange(lo, hi + 1e-9, step_km) for lo, hi in merged]))
    prev_arr = start_prev_min + prev_paces * refined
    curr_arr = start_curr_min + curr_paces * refined

    first_overlap = None
    cumulative_overlap_events = 0
    peak_congestion = 0
    unique_pairs = set()

    for idx, km in enumerate(refined):
        pt = prev_arr[:, idx]
        ct = curr_arr[:, idx]
        diff = np.abs(pt[:,None] - ct[None,:]) * 60
        hits = np.argwhere(diff <= time_window_secs)
        if hits.size:
            cumulative_overlap_events += hits.shape[0]
            for pi, ci in hits:
                unique_pairs.add((prev_df.iloc[pi]['runner_id'], curr_df.iloc[ci]['runner_id']))
            ev = np.minimum(pt[:,None], ct[None,:])[hits[:,0], hits[:,1]]
            mi = np.argmin(ev)
            p_hit, c_hit = hits[mi]
            t_hit = ev[mi]
            if (first_overlap is None or t_hit < first_overlap[0] or
                (abs(t_hit - first_overlap[0]) < 1e-9 and km < first_overlap[1])):
                first_overlap = (t_hit, km, prev_df.iloc[p_hit]['runner_id'], curr_df.iloc[c_hit]['runner_id'])
            tot = len(set(prev_df['runner_id'].iloc[hits[:,0]])) + len(set(curr_df['runner_id'].iloc[hits[:,1]]))
            if tot > peak_congestion:
                peak_congestion = tot

    return {
        'segment_start': seg_start_km, 'segment_end': seg_end_km,
        'total_prev': len(prev_df), 'total_curr': len(curr_df),
        'first_overlap': first_overlap,
        'cumulative_overlap_events': cumulative_overlap_events,
        'peak_congestion': peak_congestion,
        'unique_overlapping_pairs': len(unique_pairs)
    }

def _process_segment(df, prev_event, curr_event, start_prev, start_curr, seg_start, seg_end, desc, time_window, step_km, verbose):
    lines = []
    label = f"{seg_start:.2f}km–{seg_end:.2f}km"
    if verbose:
        lines.append(f"🔍 Checking {prev_event} vs {curr_event} from {label}...")
        if desc:
            lines.append(f"📝 Segment: {desc}")

    res = _detect_segment_overlap(df, prev_event, curr_event, start_prev, start_curr, seg_start, seg_end, time_window, step_km)
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
    record = {
        'prev_event': prev_event, 'curr_event': curr_event,
        'segment': label, 'description': desc or '',
        'intensity': intensity, 'intensity_per_km': intensity / seg_len,
        'distinct_pairs': res['unique_overlapping_pairs'],
        'peak_congestion': res['peak_congestion'],
        'peak_congestion_ratio': res['peak_congestion'] / (res['total_prev'] + res['total_curr']),
        'total_prev': res['total_prev'], 'total_curr': res['total_curr'],
        'first_overlap_time': time_str_from_minutes(res['first_overlap'][0]) if res['first_overlap'] else '',
        'first_overlap_km': f"{res['first_overlap'][1]:.2f}" if res['first_overlap'] else ''
    }

    if verbose:
        lines.append(f"🟦 Overlap segment: {label}{' ('+desc+')' if desc else ''}")
        lines.append(f"👥 Total in '{curr_event}': {record['total_curr']} runners")
        lines.append(f"👥 Total in '{prev_event}': {record['total_prev']} runners")
        if record['first_overlap_time']:
            lines.append(
                f"⚠️ First overlap at {record['first_overlap_time']} at {record['first_overlap_km']}km -> "
                f"{prev_event} Bib: {res['first_overlap'][2]}, {curr_event} Bib: {res['first_overlap'][3]}"
            )
        else:
            lines.append("✅ No overlap detected between events in this segment.")
        lines.append(f"📈 Interaction Intensity over segment: {intensity:,} (cumulative overlap events)")
        lines.append(f"🔥 Peak congestion: {res['peak_congestion']} total runners at best step")
        lines.append(f"🔁 Unique Pairs: {res['unique_overlapping_pairs']:,}")
        lines.append("")

    return lines, record

def analyze_overlaps(pace_csv: str, overlaps_csv: str, start_times: Dict[str, float],
                     time_window: int = 60, step_km: float = 0.01, verbose: bool = False,
                     rank_by: str = 'peak_ratio') -> Tuple[str, list]:
    df = pd.read_csv(pace_csv)
    overlaps = pd.read_csv(overlaps_csv)
    df.columns = [c.strip().lower() for c in df.columns]
    overlaps.columns = [c.strip().lower() for c in overlaps.columns]

    if not {'event','runner_id','pace','distance'}.issubset(df.columns):
        raise ValueError('Pace CSV missing required columns.')
    if not {'event','start','end','overlapswith'}.issubset(overlaps.columns):
        raise ValueError('Overlaps CSV missing required columns.')

    tasks = []
    for (pe, ce), grp in overlaps.groupby(['event','overlapswith']):
        if pe not in start_times or ce not in start_times:
            continue
        sp, sc = start_times[pe], start_times[ce]
        for _, r in grp.iterrows():
            tasks.append((pe, ce, sp, sc, float(r['start']), float(r['end']), r.get('description','').strip(), time_window, step_km, verbose))

    # Threads on Vercel; processes locally
    executor_cls = ThreadPoolExecutor if os.environ.get("VERCEL") else ProcessPoolExecutor

    lines = []
    records = []
    with executor_cls() as executor:
        futures = [executor.submit(_process_segment, df, *t) for t in tasks]
        for f in as_completed(futures):
            seg_lines, rec = f.result()
            lines.extend(seg_lines)
            if rec:
                records.append(rec)

    if not records:
        return "", []

    summary_df = pd.DataFrame(records)
    key = 'intensity' if rank_by == 'intensity' else 'peak_congestion_ratio'
    summary_df = summary_df.sort_values(by=key, ascending=False).reset_index(drop=True)

    lines.append("🗂️ Interaction Intensity Summary — ranked by " +
                 ("cumulative intensity" if rank_by=='intensity' else "peak congestion ratio (acute bottlenecks)") + ":")
    for i, row in summary_df.iterrows():
        suffix = f" ({row['description']})" if row['description'] else ''
        lines.append(
            f"{i+1:02d}. {row['prev_event']} vs {row['curr_event']} {row['segment']}{suffix}: "
            f"PeakRatio={row['peak_congestion_ratio']:.2%}, Peak={row['peak_congestion']}, "
            f"Intensity/km={row['intensity_per_km']:.1f}, Intensity={row['intensity']:,}, "
            f"DistinctPairs={row['distinct_pairs']:,}"
        )

    return "\n".join(lines), records
