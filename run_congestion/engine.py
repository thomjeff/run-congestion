# run_congestion/engine.py — CLI entrypoint with density subcommand
from __future__ import annotations
import argparse
import pandas as pd
from run_congestion.density import Segment, compute_density_steps, rollup_segment, render_cli_block

def _parse_start_times(s: str):
    out = {}
    for tok in s.split(","):
        if not tok.strip(): continue
        k, v = tok.split("=")
        out[k.strip()] = int(v.strip())
    return out

def _parse_segment(s: str) -> Segment:
    parts = [p.strip() for p in s.split(",")]
    if len(parts) != 6:
        raise ValueError(f"Bad segment spec: {s}")
    event_a = parts[0]
    event_b = parts[1] or None
    km_from = float(parts[2]); km_to = float(parts[3])
    width_m = float(parts[4]); direction = parts[5].lower()
    return Segment(event_a, event_b, km_from, km_to, width_m, direction)

def main(argv=None):
    parser = argparse.ArgumentParser(prog="run-congestion")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_den = sub.add_parser("density", help="Density-based congestion analysis")
    p_den.add_argument("--pace", required=True, help="Path/URL to your_pace_data.csv")
    p_den.add_argument("--start-times", required=True, help="Full=420,10K=440,Half=460")
    p_den.add_argument("--segments", required=True, help="Semicolon list: '10K,Half,0.00,2.74,3.0,uni; 10K,,2.74,5.80,1.5,bi'")
    args = parser.parse_args(argv)

    if args.cmd == "density":
        df = pd.read_csv(args.pace)
        start_times = _parse_start_times(args.start_times)
        segs = [_parse_segment(s) for s in args.segments.split(";")]
        for seg in segs:
            steps = compute_density_steps(df, seg, start_times)
            roll = rollup_segment(steps, seg)
            print(render_cli_block(roll))
            print()
        return 0

if __name__ == "__main__":
    raise SystemExit(main())
