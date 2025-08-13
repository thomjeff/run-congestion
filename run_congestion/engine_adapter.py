# run_congestion/engine_adapter.py
from run_congestion import engine as _eng

def analyze_overlaps(
    *,
    pace_csv,
    overlaps_csv,
    start_times,
    time_window: int = 60,
    step_km: float = 0.03,
    verbose: bool = False,
    rank_by: str = "peak_ratio",
    segments=None,
):
    """
    Single source of truth for parameter names used by CLI and API.
    We only accept step_km here, and we forward it to engine as step.
    """
    return _eng.analyze_overlaps(
        pace_csv=pace_csv,
        overlaps_csv=overlaps_csv,
        start_times=start_times,
        time_window=time_window,
        step=step_km,          # <-- engine uses 'step'
        verbose=verbose,
        rank_by=rank_by,
        segments=segments,
    )