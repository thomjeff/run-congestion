#!/usr/bin/env python3
import argparse
import time
from run_congestion.bridge import analyze_overlaps

def main():
    parser = argparse.ArgumentParser(description="Run overlap analysis and optionally export summary CSV.")
    parser.add_argument("pace_csv", help="Path/URL to pace CSV")
    parser.add_argument("overlaps_csv", help="Path/URL to overlaps CSV")
    parser.add_argument("--start-times", nargs="+", required=True, help="Event start times as Event=MinutesFromMidnight")
    parser.add_argument("--time-window", type=int, default=60, help="Seconds tolerance for overlap (default 60)")
    parser.add_argument("--step-km", type=float, default=0.03, help="Distance step in km (default 0.03)")
    parser.add_argument("--verbose", action="store_true", help="Print detailed per-segment output")
    parser.add_argument("--rank-by", choices=["peak_ratio","intensity"], default="peak_ratio", help="Ranking metric")
    parser.add_argument("--segments", nargs="*", help="Optional subset segments")
    parser.add_argument("--export-summary", help="Filename to export summary CSV")

    args = parser.parse_args()

    start_times = {}
    for st in args.start_times:
        k, v = st.split("=")
        start_times[k] = int(v)

    t0 = time.perf_counter()
    result = analyze_overlaps(
        pace_csv=args.pace_csv,
        overlaps_csv=args.overlaps_csv,
        start_times=start_times,
        time_window=args.time_window,
        step_km=args.step_km,
        verbose=args.verbose,
        rank_by=args.rank_by,
        segments=args.segments,
    )
    elapsed = time.perf_counter() - t0

    print(result.get("text", ""))
    print(f"⏱️ Compute time: {elapsed:.2f}s")

if __name__ == "__main__":
    main()
