# run_congestion/cli_run_and_export.py
from __future__ import annotations
import argparse
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

# Prefer adapter (adds meta, adapts step arg). Fall back to raw engine if needed.
try:
    from run_congestion.engine_adapter import analyze_overlaps
except Exception:
    from run_congestion.engine import analyze_overlaps  # type: ignore

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")

def main() -> None:
    p = argparse.ArgumentParser(description="Run overlap analysis and optionally export summary CSV to results/")
    p.add_argument("pace_csv"); p.add_argument("overlaps_csv")
    p.add_argument("--start-times", nargs="+", required=True, help="Event=MinutesFromMidnight ...")
    p.add_argument("--time-window", type=int, default=60)
    p.add_argument("--step-km", "--step", dest="step_km", type=float, default=0.03)
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--rank-by", choices=["peak_ratio","intensity"], default="peak_ratio")
    p.add_argument("--segments", nargs="*")
    p.add_argument("--export-summary", metavar="FILENAME")
    args = p.parse_args()

    # Parse start-times
    st: dict[str,float] = {}
    for kv in args.start_times:
        if "=" not in kv:
            raise SystemExit(f"Bad --start-times entry: {kv}")
        k, v = kv.split("=", 1)
        st[k.strip()] = float(v.strip())

    result = analyze_overlaps(
        pace_csv=args.pace_csv,
        overlaps_csv=args.overlaps_csv,
        start_times=st,
        time_window=args.time_window,
        step_km=args.step_km,
        verbose=args.verbose,
        rank_by=args.rank_by,
        segments=args.segments,
    )

    text = (result or {}).get("text","")
    if text: print(text)

    meta = (result or {}).get("meta",{}) or {}
    eff = float(meta.get("effective_step_km", args.step_km))
    req = float(meta.get("request_step_km", args.step_km))
    print(f"\nℹ️  Effective step used: {eff:.3f} km (requested {req:.3f} km)")
    if args.verbose:
        sps = meta.get("samples_per_segment") or {}
        if sps:
            print("   Samples per segment (distance ticks):")
            for seg, n in sorted(sps.items()):
                print(f"   • {seg}: {n} samples")

    if args.export_summary:
        out_dir = Path("results"); out_dir.mkdir(parents=True, exist_ok=True)
        # Normalize DataFrame
        df = (result or {}).get("summary_df")
        if df is not None and not hasattr(df, "to_csv"):
            df = pd.DataFrame(df)
        if df is not None:
            out_path = out_dir / f"{_ts()}_{Path(args.export_summary).name}"
            df.to_csv(out_path, index=False)
            print(f"\n✅ Wrote summary CSV to {out_path.resolve()}")
        else:
            print("⚠ No summary to export.")

if __name__ == "__main__":
    main()
