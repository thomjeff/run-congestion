
"""
Compatibility adapter so callers can always send step_km and consistent names,
even if the local engine.py uses older parameter names like `step` or `pace_path`.
"""
from __future__ import annotations

import inspect

try:
    # Prefer package-relative import
    from run_congestion.engine import analyze_overlaps as _engine_analyze_overlaps  # type: ignore
except Exception:
    # Fallback for flat layouts
    from engine import analyze_overlaps as _engine_analyze_overlaps  # type: ignore


def analyze_overlaps(
    *,
    pace_csv,
    overlaps_csv,
    start_times,
    time_window: int = 60,
    step_km: float | None = None,
    step: float | None = None,  # legacy alias
    verbose: bool = False,
    rank_by: str = "peak_ratio",
    segments=None,
):
    """
    Canonical signature expected by bridge/CLI/API.
    Dispatches to the real engine.analyze_overlaps with best-effort arg mapping.
    """
    # normalize step
    if step_km is None and step is not None:
        step_km = float(step)
    if step_km is None:
        step_km = 0.03

    # Introspect the real engine function to map known aliases
    sig = inspect.signature(_engine_analyze_overlaps)
    params = sig.parameters

    kwargs = {}
    if 'pace_csv' in params:
        kwargs['pace_csv'] = pace_csv
    elif 'pace_path' in params:
        kwargs['pace_path'] = pace_csv
    elif 'pace_df' in params:
        kwargs['pace_df'] = pace_csv  # some variants took a DF; caller passes a path/URL

    if 'overlaps_csv' in params:
        kwargs['overlaps_csv'] = overlaps_csv
    elif 'overlaps_path' in params:
        kwargs['overlaps_path'] = overlaps_csv

    if 'start_times' in params:
        kwargs['start_times'] = start_times

    if 'time_window' in params:
        kwargs['time_window'] = time_window

    # step / step_km mapping
    if 'step_km' in params:
        kwargs['step_km'] = step_km
    elif 'step' in params:
        kwargs['step'] = step_km

    if 'verbose' in params:
        kwargs['verbose'] = verbose

    if 'rank_by' in params:
        kwargs['rank_by'] = rank_by

    if 'segments' in params:
        kwargs['segments'] = segments

    return _engine_analyze_overlaps(**kwargs)
