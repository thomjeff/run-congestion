#!/usr/bin/env python3
"""
CLI launcher that normalizes args and writes timestamped CSV into results/.
Usage example:
  python3 -m run_congestion.cli_run_and_export \
    data/your_pace_data.csv \
    data/overlaps.csv \
    --start-times Full=420 10K=440 Half=460 \
    --time-window 60 \
    --step-km 0.03 \
    --verbose \
    --segments "10K:5.81-8.10" "Full:29.03-37.00" \
    --export-summary summary.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path
from datetime import datetime, UTC

from run_congestion.bridge import analyze_overlaps  # type: ignore


def _ts() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H%M%S")


def parse_start_times(items: list[str]) -> dict:
    out = {}
    for it in items:
        if "=" not in it:
            raise SystemExit(f"Bad --start-times item: {it!r} (expected Name=Minutes)")
        k, v = it.split("=", 1)
        out[k.strip()] = float(v)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Run overlap analysis and optionally export summary CSV.")
    parser.add_argument("pace_csv", help="Path/URL to pace CSV (event,runner_id,pace,distance[,start_time])")
    parser.add_argument("overlaps_csv", help="Path/URL to overlaps CSV (event,start,end,overlapswith,description)")
    parser.add_argument("--start-times", nargs="+", required=True, help="Event start times as Event=MinutesFromMidnight")
    parser.add_argument("--time-window", type=int, default=60, help="Seconds tolerance for overlap (default 60)")
    parser.add_argument("--step-km", type=float, dest="step_km", default=0.03, help="Distance step in km (default 0.03)")
    parser.add_argument("--step", type=float, dest="step_km", help=argparse.SUPPRESS)  # legacy alias
    parser.add_argument("--verbose", action="store_true", help="Print detailed per-segment output")
    parser.add_argument("--rank-by", choices=["peak_ratio", "intensity"], default="peak_ratio", help="Ranking metric")
    parser.add_argument("--segments", nargs="*", help='Optional subset, e.g. "10K:5.81-8.10" "Full:29.03-37.00"')
    parser.add_argument("--export-summary", help="Filename (e.g., summary.csv). Written under results/<timestamp>_summary.csv")
    args = parser.parse_args()

    start_times = parse_start_times(args.start_times)

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

    text = result.get("text", "")
    print(text)

    # Optional CSV export
    if args.export_summary:
        results_dir = Path("results")
        results_dir.mkdir(exist_ok=True)
        out_path = results_dir / f"{_ts()}_{Path(args.export_summary).name}"
        df = result.get("summary_df")
        if df is not None:
            try:
                import pandas as pd  # noqa: F401
                df.to_csv(out_path, index=False)
                print(f"✅ Wrote summary CSV to {out_path.resolve()}")
            except Exception as e:
                print(f"⚠️ Failed to write CSV: {e}")


if __name__ == "__main__":
    main()
