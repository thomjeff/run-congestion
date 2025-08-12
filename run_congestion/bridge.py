
from __future__ import annotations

# Always import through the adapter so argument names are stable
from run_congestion.engine_adapter import analyze_overlaps as _adapter_analyze_overlaps


def analyze_overlaps(
    *,
    pace_csv,
    overlaps_csv,
    start_times,
    time_window: int = 60,
    step_km: float | None = None,
    step: float | None = None,  # tolerated legacy alias
    verbose: bool = False,
    rank_by: str = "peak_ratio",
    segments=None,
):
    """Thin wrapper so CLI/API can call a stable function regardless of engine version."""
    # Canonicalize step
    if step_km is None and step is not None:
        step_km = float(step)
    if step_km is None:
        step_km = 0.03

    return _adapter_analyze_overlaps(
        pace_csv=pace_csv,
        overlaps_csv=overlaps_csv,
        start_times=start_times,
        time_window=time_window,
        step_km=step_km,
        verbose=verbose,
        rank_by=rank_by,
        segments=segments,
    )
