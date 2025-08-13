# run_congestion/engine_adapter.py
# Signature-adaptive wrapper: calls your existing run_congestion.engine.analyze_overlaps
# whether it expects `step_km` or `step` (or neither) and filters kwargs to supported ones.
from __future__ import annotations
import typing as _t
import inspect
import pandas as pd

try:
    from run_congestion import engine as _eng
except Exception as e:
    raise ImportError("Could not import run_congestion.engine. Ensure engine.py exists.") from e

def _supports(param_name: str, sig: inspect.Signature) -> bool:
    return param_name in sig.parameters

def _samples_per_segment(overlaps_csv: str | None, step_km: float) -> dict[str, int]:
    if not overlaps_csv:
        return {}
    try:
        df = pd.read_csv(overlaps_csv)
    except Exception:
        return {}
    df.columns = [c.strip().lower() for c in df.columns]
    req = {"event","start","end"}
    if not req.issubset(df.columns):
        return {}
    out: dict[str,int] = {}
    for _, r in df.iterrows():
        try:
            ev = str(r.get("event"))
            a = float(r.get("start")); b = float(r.get("end"))
        except Exception:
            continue
        if b < a:
            a, b = b, a
        n = int(round((b - a)/max(step_km,1e-9))) + 1
        out[f"{ev}:{a:.2f}-{b:.2f}"] = n
    return out

def analyze_overlaps(
    *,
    pace_csv: str | None = None,
    overlaps_csv: str | None = None,
    start_times: dict[str, float] | None = None,
    time_window: int = 60,
    step_km: float = 0.03,
    verbose: bool = False,
    rank_by: str = "peak_ratio",
    segments: _t.Optional[_t.List[str]] = None,
) -> dict:
    # Inspect the real engine signature
    real = getattr(_eng, "analyze_overlaps", None)
    if not callable(real):
        raise RuntimeError("run_congestion.engine.analyze_overlaps is missing")
    sig = inspect.signature(real)

    # Build adaptive kwargs
    kw: dict = {}
    # Common names used across versions
    mapping = {
        "pace_csv": pace_csv,
        "overlaps_csv": overlaps_csv,
        "start_times": start_times,
        "time_window": time_window,
        "verbose": verbose,
        "rank_by": rank_by,
        "segments": segments,
    }
    for k, v in mapping.items():
        if _supports(k, sig):
            kw[k] = v

    # Step param can be `step_km` (new) or `step` (older). Prefer engine's explicit parameter name.
    if _supports("step_km", sig):
        kw["step_km"] = step_km
    elif _supports("step", sig):
        kw["step"] = step_km
    # else: engine will compute its own default/resolution

    # Call the real function
    res = real(**kw)

    if not isinstance(res, dict):
        res = {"text": str(res), "summary_df": None}

    # Enrich with meta if not present
    meta = dict(res.get("meta", {}))
    meta.setdefault("effective_step_km", float(step_km))
    meta.setdefault("request_step_km", float(step_km))
    meta.setdefault("rank_by", rank_by)
    meta.setdefault("time_window", int(time_window))
    meta.setdefault("samples_per_segment", _samples_per_segment(overlaps_csv, float(meta["effective_step_km"])))
    res["meta"] = meta
    return res
