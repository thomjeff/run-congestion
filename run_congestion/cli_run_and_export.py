
#!/usr/bin/env python3
"""
Fixed CLI for run-congestion that avoids the 'pace_path' TypeError by
loading CSVs here and calling engine.analyze_overlaps with DataFrames.

Usage (from repo root):
  python3 -m run_congestion.cli_run_and_export \    data/your_pace_data.csv \    data/overlaps.csv \    --start-times Full=420 10K=440 Half=460 \    --time-window 60 \    --step 0.03 \    --verbose \    --segments "10K:5.81-8.10" "Full:29.03-37.00" \    --export-summary summary.csv
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

# Import the engine function
from run_congestion.engine import analyze_overlaps  # type: ignore

def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")

def _parse_segments(seg_list: Optional[List[str]]):
    if not seg_list:
        return None
    parsed = []
    for item in seg_list:
        try:
            ev, span = item.split(":", 1)
            start_s, end_s = span.split("-", 1)
            parsed.append({
                "event": ev.strip(),
                "start": float(start_s),
                "end": float(end_s)
            })
        except Exception:
            raise SystemExit(f"Invalid --segments item: {item!r}. Expected like '10K:5.81-8.10'")
    return parsed

def main():
    p = argparse.ArgumentParser(
        description="Run overlap analysis and optionally export summary CSV."
    )
    p.add_argument("pace_csv", help="Path/URL to pace CSV (event,runner_id,pace,distance[,start_time])")
    p.add_argument("overlaps_csv", help="Path/URL to overlaps CSV (event,start,end,overlapswith,description)")
    p.add_argument("--start-times", nargs="+", required=True, help="Event start times as Event=MinutesFromMidnight")
    p.add_argument("--time-window", type=int, default=60, help="Seconds tolerance for overlap (default 60)")
    p.add_argument("--step", type=float, default=0.03, help="Distance step in km (default 0.03)")
    p.add_argument("--verbose", action="store_true", help="Print detailed per-segment output")
    p.add_argument("--rank-by", choices=["peak_ratio", "intensity"], default="peak_ratio", help="Ranking metric")
    p.add_argument("--segments", nargs="*", help='Optional subset, e.g. "10K:5.81-8.10" "Full:29.03-37.00"')
    p.add_argument("--export-summary", help='Filename (e.g., summary.csv). Will be written under results/<timestamp>_summary.csv')
    args = p.parse_args()

    # Build start_times dict
    start_times: Dict[str, float] = {}
    for spec in args.start_times:
        if "=" not in spec:
            raise SystemExit(f"Bad --start-times item: {spec!r}. Expected Event=Minutes")
        ev, minutes = spec.split("=", 1)
        start_times[ev.strip()] = float(minutes)

    segments = _parse_segments(args.segments)

    # Load CSVs (local path or URL ok with pandas)
    try:
        pace_df = pd.read_csv(args.pace_csv)
        overlaps_df = pd.read_csv(args.overlaps_csv)
    except Exception as e:
        raise SystemExit(f"Failed to read CSVs: {e}")

    # Normalize columns
    pace_df.columns = [c.strip().lower() for c in pace_df.columns]
    overlaps_df.columns = [c.strip().lower() for c in overlaps_df.columns]

    # Call engine using DataFrames to avoid path-based kwargs
    request_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    result = analyze_overlaps(
        pace_df=pace_df,
        overlaps_df=overlaps_df,
        start_times=start_times,
        time_window=args.time_window,
        step_km=args.step,
        verbose=args.verbose,
        rank_by=args.rank_by,
        segments=segments,
        request_utc=request_utc  # engine is tolerant to extra kwargs; if not, remove
    )

    # Print formatted text (engine should return 'report_text')
    report_text = result.get("report_text") or result.get("text") or ""
    if report_text:
        print(report_text)

    # Optional CSV export to results/
    if args.export_summary:
        results_dir = Path("results")
        results_dir.mkdir(parents=True, exist_ok=True)
        ts = _timestamp()
        out_path = results_dir / f"{ts}_summary.csv"
        rows = result.get("summary_rows") or result.get("summary") or []
        try:
            pd.DataFrame(rows).to_csv(out_path, index=False)
            print(f"\n✅ Wrote summary CSV to {out_path}")
        except Exception as e:
            print(f"⚠️ Failed to write summary CSV: {e}")

if __name__ == "__main__":
    main()
