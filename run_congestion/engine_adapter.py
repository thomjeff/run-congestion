# run_congestion/engine_adapter.py
from run_congestion.engine import analyze_overlaps as _eng

def analyze_overlaps(*, pace_csv, overlaps_csv, start_times, time_window, step_km, verbose, rank_by, segments=None):
    # canonical path
    return _eng(
        pace_csv=pace_csv,
        overlaps_csv=overlaps_csv,
        start_times=start_times,
        time_window=time_window,
        step_km=float(step_km),
        verbose=verbose,
        rank_by=rank_by,
        segments=segments,
    )