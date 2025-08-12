#!/usr/bin/env python3
import argparse
from pathlib import Path
from datetime import datetime
import pandas as pd

# Prefer the bridge API if present; fall back to engine
try:
    from run_congestion.bridge import analyze_overlaps, parse_start_times
except Exception:
    from run_congestion.engine import analyze_overlaps
    try:
        from run_congestion.engine import parse_start_times
    except Exception:
        # Local fallback if engine doesn't export parse_start_times
        def parse_start_times(pairs):
            mapping = {}
            for p in pairs:
                if '=' not in p:
                    raise ValueError(f"Invalid start time spec: {p}. Expected Format Event=minutes_since_midnight")
                event, val = p.split('=', 1)
                mapping[event.strip()] = float(val)
            return mapping

def main():
    parser = argparse.ArgumentParser(description="Run overlap analysis and export results to results/ folder.")
    parser.add_argument("pace_csv", help="Path or URL to pace CSV (event, runner_id, pace, distance)")
    parser.add_argument("overlaps_csv", help="Path or URL to overlaps CSV (event,start,end,overlapsWith,description)")
    parser.add_argument("--start-times", nargs="+", required=True, help="Event start times in format Name=MinutesFromMidnight")
    parser.add_argument("--time-window", type=int, default=60, help="Overlap detection window in seconds")
    parser.add_argument("--step", type=float, default=0.03, help="Step in km for simulation")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--rank-by", choices=["peak_ratio", "intensity"], default="peak_ratio", help="Ranking metric")
    args = parser.parse_args()

    # Resolve output folder relative to this script
    repo_root = Path(__file__).resolve().parent
    results_dir = repo_root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    out_csv = results_dir / f"{timestamp}_summary.csv"

    start_times = parse_start_times(args.start_times)

    # Call with the signature used by your working CLI
    # analyze_overlaps(pace_csv, overlaps_csv, start_times, time_window=..., step_km=..., verbose=..., rank_by=...)
    result = analyze_overlaps(
        args.pace_csv,
        args.overlaps_csv,
        start_times,
        time_window=args.time_window,
        step_km=args.step,
        verbose=args.verbose,
        rank_by=args.rank_by
    )

    # Normalize return shape: tuple(text, records) or dict with keys
    report_text = ""
    summary_records = []
    if isinstance(result, tuple) and len(result) >= 2:
        report_text, summary_records = result[0], result[1]
    elif isinstance(result, dict):
        report_text = result.get("reportText", "")
        summary_records = result.get("summary", [])
    else:
        # Best effort: print whatever came back
        report_text = str(result)

    # Emit terminal output
    if report_text.strip():
        print(report_text.rstrip())
    else:
        print("✅ No overlapping segments detected.")

    # Persist CSV
    df = pd.DataFrame(summary_records)
    df.to_csv(out_csv, index=False)
    print(f"✅ Wrote summary CSV to {out_csv}")

if __name__ == "__main__":
    main()
