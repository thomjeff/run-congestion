#!/usr/bin/env python3

import argparse
import pandas as pd
import numpy as np
import time
from datetime import datetime, timezone
import os

DEFAULT_TIME_WINDOW_SECONDS = 60
DEFAULT_STEP_KM = 0.01

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
    time_window_secs=DEFAULT_TIME_WINDOW_SECONDS,
    step_km=DEFAULT_STEP_KM
):
    prev_df = df[df["event"] == prev_event].copy()
    curr_df = df[df["event"] == curr_event].copy()
    if prev_df.empty or curr_df.empty:
        return None

    steps = np.arange(seg_start_km, seg_end_km + 1e-9, step_km)

    prev_arrivals = {row["runner_id"]: start_prev_min + row["pace"] * steps
                     for _, row in prev_df.iterrows()}
    curr_arrivals = {row["runner_id"]: start_curr_min + row["pace"] * steps
                     for _, row in curr_df.iterrows()}

    first_overlap = None
    cumulative_overlap_events = 0
    peak_congestion = 0
    peak_prev = set()
    peak_curr = set()
    unique_pairs = set()

    for si, km in enumerate(steps):
        prev_ids = list(prev_arrivals.keys())
        curr_ids = list(curr_arrivals.keys())
        prev_times_arr = np.array([prev_arrivals[rid][si] for rid in prev_ids])
        curr_times_arr = np.array([curr_arrivals[rid][si] for rid in curr_ids])

        time_diff = np.abs(prev_times_arr[:, None] - curr_times_arr[None, :]) * 60
        overlap_mask = time_diff <= time_window_secs

        num_hits = int(overlap_mask.sum())
        cumulative_overlap_events += num_hits

        hits = np.nonzero(overlap_mask)
        for p_idx, c_idx in zip(*hits):
            unique_pairs.add((prev_ids[p_idx], curr_ids[c_idx]))

        overlapping_prev = {prev_ids[i] for i in np.unique(hits[0])} if hits[0].size else set()
        overlapping_curr = {curr_ids[i] for i in np.unique(hits[1])} if hits[1].size else set()

        if hits[0].size:
            prev_matrix = np.broadcast_to(prev_times_arr[:, None], time_diff.shape)
            curr_matrix = np.broadcast_to(curr_times_arr[None, :], time_diff.shape)
            event_times_matrix = np.minimum(prev_matrix, curr_matrix)
            candidate_times = event_times_matrix[overlap_mask]
            min_idx_flat = np.argmin(candidate_times)
            overlapping_indices = np.column_stack(np.nonzero(overlap_mask))
            first_p_idx, first_c_idx = overlapping_indices[min_idx_flat]
            event_time = event_times_matrix[first_p_idx, first_c_idx]
            if (first_overlap is None or
                (event_time < first_overlap[0]) or
                (abs(event_time - first_overlap[0]) < 1e-6 and km < first_overlap[1])
            ):
                first_overlap = (event_time, km, prev_ids[first_p_idx], curr_ids[first_c_idx])

        total_overlapping_runners = len(overlapping_prev) + len(overlapping_curr)
        if total_overlapping_runners > peak_congestion:
            peak_congestion = total_overlapping_runners
            peak_prev = overlapping_prev.copy()
            peak_curr = overlapping_curr.copy()

    return {
        "segment_start": seg_start_km,
        "segment_end": seg_end_km,
        "total_prev": len(prev_df),
        "total_curr": len(curr_df),
        "first_overlap": first_overlap,
        "cumulative_overlap_events": cumulative_overlap_events,
        "peak_congestion": peak_congestion,
        "peak_prev_at_peak": peak_prev,
        "peak_curr_at_peak": peak_curr,
        "unique_overlapping_pairs": len(unique_pairs)
    }

def main():
    parser = argparse.ArgumentParser(
        description="Detect runner overlaps between events on shared course segments."
    )
    parser.add_argument("pace_csv", help="CSV with runner data (event, runner_id, pace, distance)")
    parser.add_argument("overlaps_csv", help="CSV defining overlapping segments (see README)")
    parser.add_argument(
        "--start-times", "-s", nargs="+", required=True,
        help="Event start times in minutes since midnight, e.g. Full=420 10K=440 Half=460"
    )
    parser.add_argument(
        "--time-window", type=int, default=DEFAULT_TIME_WINDOW_SECONDS,
        help="Seconds tolerance for overlap (default 60)"
    )
    parser.add_argument(
        "--step", type=float, default=DEFAULT_STEP_KM,
        help="Distance resolution in km (default 0.01)"
    )
    parser.add_argument("--verbose", action="store_true", help="More detail")
    parser.add_argument("--export-summary", help="Path to CSV to dump the summary")
    parser.add_argument("--rank-by", choices=["intensity", "peak_ratio"], default="peak_ratio",
                        help="Metric to rank summary by (default: peak_ratio)")

    args = parser.parse_args()

    df = pd.read_csv(args.pace_csv)
    overlaps = pd.read_csv(args.overlaps_csv)

    df.columns = [c.strip().lower() for c in df.columns]
    overlaps.columns = [c.strip().lower() for c in overlaps.columns]

    required_pace = {"event", "runner_id", "pace", "distance"}
    if not required_pace.issubset(set(df.columns)):
        raise SystemExit(f"Pace CSV missing required columns. Found: {df.columns.tolist()}")
    if not {"event", "start", "end", "overlapswith"}.issubset(set(overlaps.columns)):
        raise SystemExit(f"Overlaps CSV missing required columns. Found: {overlaps.columns.tolist()}")

    start_times = parse_start_times(args.start_times)
    all_results = []

    for (prev_event, curr_event), group in overlaps.groupby(["event", "overlapswith"]):
        if prev_event not in start_times or curr_event not in start_times:
            continue
        start_prev = start_times[prev_event]
        start_curr = start_times[curr_event]
        for _, row in group.iterrows():
            seg_start = float(row["start"])
            seg_end = float(row["end"])
            desc = row.get("description", "").strip()
            segment_label = f"{seg_start:.2f}km–{seg_end:.2f}km"
            if args.verbose:
                print(f"🔍 Checking {prev_event} vs {curr_event} from {seg_start:.2f}km to {seg_end:.2f}km...")
                if desc:
                    print(f"📝 Segment: {desc}")
            t0 = time.perf_counter()
            result = detect_segment_overlap(
                df, prev_event, curr_event,
                start_prev, start_curr,
                seg_start, seg_end,
                time_window_secs=args.time_window,
                step_km=args.step
            )
            t1 = time.perf_counter()
            runtime = t1 - t0
            if result is None:
                if args.verbose:
                    print(f"🟦 Overlap segment: {seg_start:.2f} km → {seg_end:.2f} km" + (f" ({desc})" if desc else ""))
                    print(f"👥 Total in '{curr_event}': 0 runners")
                    print(f"👥 Total in '{prev_event}': 0 runners")
                    print(f"✅ No overlap detected between events in this segment.")
                    print()
                continue

            intensity = result["cumulative_overlap_events"]
            seg_length = max(1e-9, seg_end - seg_start)
            intensity_per_km = intensity / seg_length
            peak_ratio = result["peak_congestion"] / (result["total_prev"] + result["total_curr"]) if (result["total_prev"] + result["total_curr"]) > 0 else 0

            record = {
                "prev_event": prev_event,
                "curr_event": curr_event,
                "segment": segment_label,
                "description": desc,
                "intensity": intensity,
                "intensity_per_km": intensity_per_km,
                "distinct_pairs": result["unique_overlapping_pairs"],
                "peak_congestion": result["peak_congestion"],
                "peak_congestion_ratio": peak_ratio,
                "total_prev": result["total_prev"],
                "total_curr": result["total_curr"],
                "start_prev": start_prev,
                "start_curr": start_curr,
                "time_window": args.time_window,
                "step": args.step,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "first_overlap_time": time_str_from_minutes(result["first_overlap"][0]) if result["first_overlap"] else "",
                "first_overlap_km": f"{result['first_overlap'][1]:.2f}" if result["first_overlap"] else "",
                "first_overlap_prev_runner": result["first_overlap"][2] if result["first_overlap"] else "",
                "first_overlap_curr_runner": result["first_overlap"][3] if result["first_overlap"] else "",
                "runtime_seconds": runtime,
            }
            all_results.append(record)

            if args.verbose:
                print(f"🟦 Overlap segment: {seg_start:.2f} km → {seg_end:.2f} km" + (f" ({desc})" if desc else ""))
                print(f"👥 Total in '{curr_event}': {result['total_curr']} runners")
                print(f"👥 Total in '{prev_event}': {result['total_prev']} runners")
                if result["first_overlap"]:
                    time_str = time_str_from_minutes(result["first_overlap"][0])
                    print(f"⚠️ First overlap at {time_str} at {result['first_overlap'][1]:.2f}km -> {prev_event} Bib: {result['first_overlap'][2]}, {curr_event} Bib: {result['first_overlap'][3]}")
                else:
                    print("✅ No overlap detected between events in this segment.")
                print(f"📈 Interaction Intensity over segment: {result['cumulative_overlap_events']:,} (cumulative overlap events)")
                print(f"🔥 Peak congestion: {result['peak_congestion']} total runners at best step ({len(result['peak_prev_at_peak'])} from '{prev_event}', {len(result['peak_curr_at_peak'])} from '{curr_event}')")
                print(f"🔁 Unique Pairs: {result['unique_overlapping_pairs']:,} (cross-bib relationships with at least one overlap)")
                print(f"   ⏱ Segment runtime: {runtime:.3f}s")
                print()

    if all_results:
        summary_df = pd.DataFrame(all_results)
        sort_key = "intensity" if args.rank_by == "intensity" else "peak_congestion_ratio"
        summary_df = summary_df.sort_values(by=sort_key, ascending=False).reset_index(drop=True)
        heading = "cumulative intensity" if args.rank_by == "intensity" else "peak congestion ratio (acute bottlenecks)"
        print(f"🗂️ Interaction Intensity Summary — ranked by {heading}:")
        for idx, row in summary_df.iterrows():
            desc_suffix = f" ({row['description']})" if row.get("description") else ""
            print(f"{idx+1:02d}. {row['prev_event']} vs {row['curr_event']} {row['segment']}{desc_suffix}: "
                  f"PeakRatio={row['peak_congestion_ratio']:.2%}, Peak={row['peak_congestion']}, Intensity/km={row['intensity_per_km']:.1f}, "
                  f"Intensity={row['intensity']:,}, DistinctPairs={row['distinct_pairs']:,}")
        print()

    if args.export_summary:
        # build a clean timestamp prefix
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")

        # figure out where to write: use provided dir or default to 'examples'
        provided = args.export_summary
        base, ext = os.path.splitext(os.path.basename(provided))
        directory = os.path.dirname(provided) or "examples"
        os.makedirs(directory, exist_ok=True)

        # final filename: e.g. '2025-08-06T133027_summary.csv'
        out_filename = os.path.join(directory, f"{now_str}_{base}{ext or '.csv'}")

        # write only the dated file
        summary_df.to_csv(out_filename, index=False)
        print(f"✅ Wrote summary CSV to {out_filename}")    

if __name__ == "__main__":
    main()
