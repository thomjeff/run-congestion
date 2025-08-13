# run_congestion/engine_adapter.py
"""
Compatibility shim so callers can always use step_km, regardless of the engine's
current parameter name (step vs step_km).
"""
from typing import Dict, Optional, Sequence, Union
import inspect
from run_congestion import engine as _eng

def _engine_accepts(name: str) -> bool:
    try:
        sig = inspect.signature(_eng.analyze_overlaps)
        return name in sig.parameters
    except Exception:
        return False

def analyze_overlaps(
    *,
    pace_csv: Union[str, bytes],
    overlaps_csv: Union[str, bytes],
    start_times: Dict[str, float],
    time_window: int = 60,
    step_km: float = 0.03,
    verbose: bool = False,
    rank_by: str = "peak_ratio",
    segments: Optional[Sequence[str]] = None,
) -> Dict[str, object]:
    """
    Always accept step_km from callers.
    Forward to engine.analyze_overlaps, translating to either `step` or `step_km`.
    """
    kwargs = dict(
        pace_csv=pace_csv,
        overlaps_csv=overlaps_csv,
        start_times=start_times,
        time_window=time_window,
        verbose=verbose,
        rank_by=rank_by,
        segments=segments,
    )

    if _engine_accepts("step"):      # legacy/newer variant using `step`
        kwargs["step"] = step_km
    else:                            # variant using `step_km`
        kwargs["step_km"] = step_km

    return _eng.analyze_overlaps(**kwargs)  # type: ignore[arg-type]