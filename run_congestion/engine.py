import os
import time
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
    prev_df = df[df['event'] == prev_event].copy()
    curr_df = df[df['event'] == curr_event].copy()
    if prev_df.empty or curr_df.empty:
        return None

    steps = np.arange(seg_start_km, seg_end_km + 1e-9, step_km)

    prev_arrivals = np.array([start_prev_min + row['pace'] * steps for _, row in prev_df.iterrows()])
    curr_arrivals = np.array([start_curr_min + row['pace'] * steps for _, row in curr_df.iterrows()])

    first_overlap = None
    cumulative_overlap_events = 0
    peak_congestion = 0
    peak_prev = set()
    peak_curr = set()
    unique_pairs = set()

    for si, km in enumerate(steps):
        prev_times = prev_arrivals[:, si]
        curr_times = curr_arrivals[:, si]
        # compute pairwise differences
        diff = np.abs(prev_times[:, None] - curr_times[None, :]) * 60
        mask = diff <= time_window_secs
        hits = np.argwhere(mask)
        if hits.size > 0:
            cumulative_overlap_events += hits.shape[0]
            # unique pairs
            for p_idx, c_idx in hits:
                unique_pairs.add((prev_df.iloc[p_idx]['runner_id'],
                                  curr_df.iloc[c_idx]['runner_id']))
            # update first overlap
            event_times = np.minimum(prev_times[:, None], curr_times[None, :])
            overlap_times = event_times[mask]
            min_idx_flat = np.argmin(overlap_times)
            p_idx, c_idx = hits[min_idx_flat]
            event_time = overlap_times[min_idx_flat]
            if (first_overlap is None or
                event_time < first_overlap[0] or
                (abs(event_time - first_overlap[0]) < 1e-6 and km < first_overlap[1])):
                first_overlap = (event_time, km,
                                 prev_df.iloc[p_idx]['runner_id'],
                                 curr_df.iloc[c_idx]['runner_id'])
        # peak congestion
        if hits.size > 0:
            overlapping_prev = set(prev_df['runner_id'].iloc[hits[:,0]])
            overlapping_curr = set(curr_df['runner_id'].iloc[hits[:,1]])
            total = len(overlapping_prev) + len(overlapping_curr)
            if total > peak_congestion:
                peak_congestion = total
                peak_prev = overlapping_prev
                peak_curr = overlapping_curr

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
    # load inputs
    df = pd.read_csv(pace_csv)
    overlaps = pd.read_csv(overlaps_csv)

    # normalize column names
    df.columns = [c.strip().lower() for c in df.columns]
    overlaps.columns = [c.strip().lower() for c in overlaps.columns]

    # validate required columns
    if not {'event','runner_id','pace','distance'}.issubset(df.columns):
        raise ValueError('Pace CSV missing required columns')
    if not {'event','start','end','overlapswith'}.issubset(overlaps.columns):
        raise ValueError('Overlaps CSV missing required columns')

    lines = []
    all_results = []

    # parse and iterate segments
    for (prev_event, curr_event), grp in overlaps.groupby(['event','overlapswith']):
        if prev_event not in start_times or curr_event not in start_times:
            continue
        start_prev = start_times[prev_event]
        start_curr = start_times[curr_event]
        for _, row in grp.iterrows():
            seg_start = float(row['start'])
            seg_end = float(row['end'])
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
                    lines.append(f"🟦 Overlap segment: {segment_label} ({desc})" if desc else f"🟦 Overlap segment: {segment_label}")
                    lines.append(f"👥 Total in '{curr_event}': 0 runners")
                    lines.append(f"👥 Total in '{prev_event}': 0 runners")
                    lines.append("✅ No overlap detected between events in this segment.")
                    lines.append("" )
                continue

            intensity = result['cumulative_overlap_events']
            seg_len = max(1e-9, seg_end - seg_start)
            intensity_per_km = intensity / seg_len
            peak_ratio = result['peak_congestion'] / (result['total_prev'] + result['total_curr'])

            # record summary
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
                'first_overlap_km': f"{result['first_overlap'][1]:.2f}" if result['first_overlap'] else '',
            }
            all_results.append(record)

            if verbose:
                lines.append(f"🟦 Overlap segment: {segment_label} ({desc})" if desc else f"🟦 Overlap segment: {segment_label}")
                lines.append(f"👥 Total in '{curr_event}': {record['total_curr']} runners")
                lines.append(f"👥 Total in '{prev_event}': {record['total_prev']} runners")
                if record['first_overlap_time']:
                    lines.append(f"⚠️ First overlap at {record['first_overlap_time']} at {record['first_overlap_km']}km -> {prev_event} Bib: {result['first_overlap'][2]}, {curr_event} Bib: {result['first_overlap'][3]}")
                else:
                    lines.append("✅ No overlap detected between events in this segment.")
                lines.append(f"📈 Interaction Intensity over segment: {intensity:,} (cumulative overlap events)")
                lines.append(f"🔥 Peak congestion: {result['peak_congestion']} total runners at best step")  
                lines.append("🔁 Unique Pairs: {0:,} (cross-bib relationships)".format(result['unique_overlapping_pairs']))
                lines.append("" )

    # build ranked summary
    if not all_results:
        report_text = "No overlapping segments processed."
        return report_text, []

    summary_df = pd.DataFrame(all_results)
    sort_key = 'intensity' if rank_by == 'intensity' else 'peak_congestion_ratio'
    summary_df = summary_df.sort_values(by=sort_key, ascending=False).reset_index(drop=True)

    lines.append("🗂️ Interaction Intensity Summary — ranked by " + ("cumulative intensity" if rank_by=='intensity' else "peak congestion ratio (acute bottlenecks)" ) + ":")
    for idx, row in summary_df.iterrows():
        desc_suffix = f" ({row['description']})" if row['description'] else ''
        lines.append(f"{idx+1:02d}. {row['prev_event']} vs {row['curr_event']} {row['segment']}{desc_suffix}: PeakRatio={row['peak_congestion_ratio']:.2%}, Peak={row['peak_congestion']}, Intensity/km={row['intensity_per_km']:.1f}, Intensity={row['intensity']:,}, DistinctPairs={row['distinct_pairs']:,}")

    report_text = "\n".join(lines)
    return report_text, all_results
