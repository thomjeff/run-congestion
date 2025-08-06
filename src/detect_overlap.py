#!/usr/bin/env python3
import argparse
import os
from datetime import datetime
import pandas as pd

from run_congestion.engine import parse_start_times, analyze_overlaps

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
        "--time-window", type=int, default=60,
        help="Seconds tolerance for overlap (default 60)"
    )
    parser.add_argument(
        "--step", type=float, default=0.01,
        help="Distance resolution in km (default 0.01)"
    )
    parser.add_argument(
        "--rank-by", choices=["peak_ratio", "intensity"], default="peak_ratio",
        help="How to rank the summary: 'peak_ratio' (default) or 'intensity'"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print detailed per-segment output"
    )
    parser.add_argument(
        "--export-summary", "-e", metavar="FILE",
        help="Write summary CSV with timestamp prefix into the directory you specify"
    )

    args = parser.parse_args()

    # Parse and run
    start_times = parse_start_times(args.start_times)
    start_dt = datetime.now()

    report_text, summary = analyze_overlaps(
        args.pace_csv,
        args.overlaps_csv,
        start_times,
        time_window=args.time_window,
        step_km=args.step,
        verbose=args.verbose,
        rank_by=args.rank_by
    )

    # Print report
    print(report_text)

    # Export summary if requested
    if args.export_summary:
        now_str = datetime.now().strftime("%Y-%m-%dT%H%M%S")
        base, ext = os.path.splitext(os.path.basename(args.export_summary))
        directory = os.path.dirname(args.export_summary) or "."
        os.makedirs(directory, exist_ok=True)
        out_filename = os.path.join(directory, f"{now_str}_{base}{ext or '.csv'}")

        df = pd.DataFrame(summary)
        df.to_csv(out_filename, index=False)
        print(f"✅ Wrote summary CSV to {os.path.abspath(out_filename)}")

    # Print timing
    elapsed = (datetime.now() - start_dt).total_seconds()
    print(f"⏱ Total computation time: {elapsed:.2f} seconds")


if __name__ == "__main__":
    main()
