#!/usr/bin/env python3
import os
import sys

# Ensure parent directory is on PYTHONPATH so run_congestion package is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import argparse
from datetime import datetime, timezone
import pandas as pd

from run_congestion.engine import analyze_overlaps, parse_start_times

def main():
    parser = argparse.ArgumentParser(description="Run-congestion CLI (v1.0.0)")
    parser.add_argument("pace_csv", help="Path to pace CSV (event, runner_id, pace, distance)")
    parser.add_argument("overlaps_csv", help="Path to overlaps CSV (event, start, end, overlapswith, description)")
    parser.add_argument(
        "--start-times", "-s", nargs="+", required=True,
        help="Event start times as Event=minutes_since_midnight, e.g. Full=420 10K=440 Half=460"
    )
    parser.add_argument(
        "--time-window", type=int, default=60,
        help="Seconds tolerance for overlap (default: 60)"
    )
    parser.add_argument(
        "--step", type=float, default=0.01,
        help="Distance resolution in km (default: 0.01)"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print detailed per-segment output"
    )
    parser.add_argument(
        "--export-summary", help="Path to write summary CSV (will be prefixed with timestamp)"
    )
    parser.add_argument(
        "--rank-by", choices=["intensity", "peak_ratio"], default="peak_ratio",
        help="Ranking metric for summary (default: peak_ratio)"
    )

    args = parser.parse_args()

    # Parse start times into a mapping
    start_times = parse_start_times(args.start_times)

    # Run core analysis
    report_text, summary = analyze_overlaps(
        args.pace_csv,
        args.overlaps_csv,
        start_times,
        args.time_window,
        args.step,
        args.verbose,
        args.rank_by
    )

    # Output to terminal
    print(report_text)

    # Optionally export summary CSV
    if args.export_summary:
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
        base, ext = os.path.splitext(os.path.basename(args.export_summary))
        directory = os.path.dirname(args.export_summary) or "examples"
        os.makedirs(directory, exist_ok=True)
        out_filename = os.path.join(directory, f"{now_str}_{base}{ext or '.csv'}")
        df = pd.DataFrame(summary)
        df.to_csv(out_filename, index=False)
        print(f"✅ Wrote summary CSV to {out_filename}")

if __name__ == "__main__":
    main()
