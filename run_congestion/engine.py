import os
import pandas as pd
import numpy as np
from datetime import datetime, timezone

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
    df, prev_event, curr_event,
    start_prev_min, start_curr_min,
    seg_start_km, seg_end_km,
    time_window_secs=60,
    step_km=0.01
):
    # Filter dataframes by event
    prev_df = df[df['event'] == prev_event].copy().reset_index(drop=True)
    curr_df = df[df['event'] == curr_event].copy().reset_index(drop=True)
    if prev_df.empty or curr_df.empty:
        return None

    # Pre-filter based on arrival windows
    prev_start = start_prev_min + prev_df['pace'] * seg_start_km
    prev_end   = start_prev_min + prev_df['pace'] * seg_end_km
    curr_start = start_curr_min + curr_df['pace'] * seg_start_km
    curr_end   = start_curr_min + curr_df['pace'] * seg_end_km

    prev_min = prev_start.values
    prev_max = prev_end.values
    curr_min = curr_start.values
    curr_max = curr_end.values

    mask = (prev_max[:, None] >= curr_min[None, :]) & (curr_max[None, :] >= prev_min[:, None])
    prev_keep = mask.any(axis=1)
    curr_keep = mask.any(axis=0)

    prev_df = prev_df.loc[prev_keep].reset_index(drop=True)
    curr_df = curr_df.loc[curr_keep].reset_index(drop=True)
    if prev_df.empty or curr_df.empty:
        return None

    # Compute steps
    steps = np.arange(seg_start_km, seg_end_km + 1e-9, step_km)

    # Vectorized arrival times: broadcasting
    prev_paces = prev_df['pace'].to_numpy()[:, None]  # shape (n_prev, 1)
    curr_paces = curr_df['pace'].to_numpy()[:, None]  # shape (n_curr, 1)
    prev_arr = start_prev_min + prev_paces * steps      # shape (n_prev, n_steps)
    curr_arr = start_curr_min + curr_paces * steps     # shape (n_curr, n_steps)

    first_overlap = None
    cumulative_overlap_events = 0
    peak_congestion = 0
    peak_prev = set()
    peak_curr = set()
    unique_pairs = set()

    for si, km in enumerate(steps):
        prev_times = prev_arr[:, si]
        curr_times = curr_arr[:, si]
        diff = np.abs(prev_times[:, None] - curr_times[None, :]) * 60
        hits = np.argwhere(diff <= time_window_secs)

        if hits.size:
            cumulative_overlap_events += hits.shape[0]
            for p_idx, c_idx in hits:
                unique_pairs.add((prev_df.iloc[p_idx]['runner_id'],
                                  curr_df.iloc[c_idx]['runner_id']))
            ev_times = np.minimum(prev_times[:, None], curr_times[None, :])[hits[:,0], hits[:,1]]
            idx = np.argmin(ev_times)
            p_idx, c_idx = hits[idx]
            event_time = ev_times[idx]
            if (first_overlap is None or
                event_time < first_overlap[0] or
                (abs(event_time - first_overlap[0]) < 1e-6 and km < first_overlap[1])):
                first_overlap = (event_time, km,
                                 prev_df.iloc[p_idx]['runner_id'],
                                 curr_df.iloc[c_idx]['runner_id'])
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

def analyze_overlaps(
    pace_csv, overlaps_csv, start_times,
    time_window=60, step_km=0.01,
    verbose=False, rank_by='peak_ratio'
):
    df = pd.read_csv(pace_csv)
    overlaps = pd.read_csv(overlaps_csv)
    df.columns = [c.strip().lower() for c in df.columns]
    overlaps.columns = [c.strip().lower() for c in overlaps.columns]

    required_pace = {'event','runner_id','pace','distance'}
    if not required_pace.issubset(df.columns):
        raise ValueError('Pace CSV missing required columns.')
    if not {'event','start','end','overlapswith'}.issubset(overlaps.columns):
        raise ValueError('Overlaps CSV missing required columns.')

    lines = []
    all_results = []

    for (prev_event, curr_event), grp in overlaps.groupby(['event','overlapswith']):
        if prev_event not in start_times or curr_event not in start_times:
            continue
        start_prev = start_times[prev_event]
        start_curr = start_times[curr_event]
        for _, row in grp.iterrows():
            seg_start = float(row['start'])
            seg_end   = float(row['end'])
            desc = row.get('description','').strip()
            segment_label = f"{seg_start:.2f}km–{seg_end:.2f}km"
            if verbose:
                lines.append(f"🔍 Checking {prev_event} vs {curr_event} from {segment_label}...")
                if desc:
                    lines.append(f"📝 Segment: {desc}")
            result = detect_segment_overlap(
                df, prev_event, curr_event,
                start_prev, start_curr,
                seg_start, seg_end,
                time_window, step_km
            )
            if result is None:
                if verbose:
                    lines.append(f"🟦 Overlap segment: {segment_label}{' ('+desc+')' if desc else ''}")
                    lines.append(f"👥 Total in '{curr_event}': 0 runners")
                    lines.append(f"👥 Total in '{prev_event}': 0 runners")
                    lines.append("✅ No overlap detected between events in this segment.")
                    lines.append("")
                continue

            intensity = result['cumulative_overlap_events']
            seg_len = max(1e-9, seg_end - seg_start)
            intensity_per_km = intensity / seg_len
            peak_ratio = result['peak_congestion'] / (result['total_prev'] + result['total_curr'])

            record = {
                'prev_event': prev_event,
                'curr_event': curr_event,
                'segment': segment_label,
                'description': desc,
                'intensity': intensity,
                'intensity_per_km': intensity_per_km,
                'distinct_pairs': result['unique_overlapping_pairs'],
                'peak_congestion': result['peak_congestion'],
                'peak_congestion_ratio': peak_ratio,
                'total_prev': result['total_prev'],
                'total_curr': result['total_curr'],
                'first_overlap_time': time_str_from_minutes(result['first_overlap'][0]) if result['first_overlap'] else '',
                'first_overlap_km': f"{result['first_overlap'][1]:.2f}" if result['first_overlap'] else ''
            }
            all_results.append(record)

            if verbose:
                lines.append(f"🟦 Overlap segment: {segment_label}{' ('+desc+')' if desc else ''}")
                lines.append(f"👥 Total in '{curr_event}': {record['total_curr']} runners")
                lines.append(f"👥 Total in '{prev_event}': {record['total_prev']} runners")
                if record['first_overlap_time']:
                    lines.append(f"⚠️ First overlap at {record['first_overlap_time']} at {record['first_overlap_km']}km -> {prev_event} Bib: {result['first_overlap'][2]}, {curr_event} Bib: {result['first_overlap'][3]}")
                else:
                    lines.append("✅ No overlap detected between events in this segment.")
                lines.append(f"📈 Interaction Intensity over segment: {intensity:,} (cumulative overlap events)")
                lines.append(f"🔥 Peak congestion: {result['peak_congestion']} total runners at best step ( {len(result['peak_prev_at_peak'])} from '{prev_event}', {len(result['peak_curr_at_peak'])} from '{curr_event}' )")
                lines.append(f"🔁 Unique Pairs: {result['unique_overlapping_pairs']:,} (cross-bib relationships)")
                lines.append("")

    if not all_results:
        return "No overlapping segments processed.", []

    summary_df = pd.DataFrame(all_results)
    sort_key = 'intensity' if rank_by == 'intensity' else 'peak_congestion_ratio'
    summary_df = summary_df.sort_values(by=sort_key, ascending=False).reset_index(drop=True)

    lines.append("🗂️ Interaction Intensity Summary — ranked by " +
                 ("cumulative intensity" if rank_by=='intensity' else "peak congestion ratio (acute bottlenecks)") + ":")
    for idx, row in summary_df.iterrows():
        desc_suffix = f" ({row['description']})" if row['description'] else ''
        lines.append(f"{idx+1:02d}. {row['prev_event']} vs {row['curr_event']} {row['segment']}{desc_suffix}: PeakRatio={row['peak_congestion_ratio']:.2%}, Peak={row['peak_congestion']}, Intensity/km={row['intensity_per_km']:.1f}, Intensity={row['intensity']:,}, DistinctPairs={row['distinct_pairs']:,}")

    report_text = "\n".join(lines)
    return report_text, all_results
