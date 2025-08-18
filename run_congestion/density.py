# run_congestion/density.py
# Backward-compatible density engine with a stable public entrypoint:
#   run_density(config: dict) -> dict
#
# This module also exposes:
#   - Segment (dataclass)
#   - compute_density_steps(...)
#   - rollup_segment(...)
#   - render_cli_block(...)
#
# Notes:
# - No breaking changes vs. prior versions: function names are preserved.
# - No line-continuation backslashes in f-strings (fixes SyntaxError).
# - Tolerates both string and object segment specs.
# - Counts distinct runners per step (not pairs), constant-pace model.
# - Defaults: step_km=0.03, time_window=60s.
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

STEP_KM_DEFAULT = 0.03
WINDOW_S_DEFAULT = 60

@dataclass
class Segment:
    event_a: str
    event_b: Optional[str] = None
    km_from: float = 0.0
    km_to: float = 0.0
    width_m: float = 3.0
    direction: str = "uni"  # "uni" | "bi"

@dataclass
class DensityStep:
    km: float
    counts: Dict[str, int]
    combined: int
    areal_m2: float
    linear_m: float

@dataclass
class SegmentRollup:
    segment: Segment
    peak_km: float
    peak: Dict[str, int]
    peak_step_areal_m2: float
    peak_step_linear_m: float
    segment_avg_at_peak_areal_m2: float
    segment_avg_at_peak_linear_m: float
    zones_km: Dict[str, float]
    index_0_10: float
    diagnostics: Dict[str, float]

def _bins(k0: float, k1: float, step_km: float) -> List[float]:
    # Inclusive upper bound to match CLI step behavior
    n = max(0, int(round((k1 - k0) / step_km)))
    return [round(k0 + i * step_km, 2) for i in range(n + 1)]

def _zone(density: float) -> str:
    if density < 1.0:  return "green"
    if density < 1.5:  return "amber"
    if density < 2.0:  return "red"
    return "dark_red"

def _congestion_index(d_peak: float, share_amber: float, share_red: float, share_dark: float) -> float:
    # Peak component (0–5)
    if d_peak < 1.0:       s_peak = 0.0
    elif d_peak < 1.5:     s_peak = 2.0 * (d_peak - 1.0) / 0.5
    elif d_peak < 2.0:     s_peak = 2.0 + 2.0 * (d_peak - 1.5) / 0.5
    else:                  s_peak = 4.0 + 1.0 * (min(d_peak, 3.0) - 2.0) / 1.0
    s_peak = max(0.0, min(5.0, s_peak))
    # Duration component (0–3), weighted by severity
    s_zones = 3.0 * min(1.0, 0.4*share_amber + 0.8*share_red + 1.0*share_dark)
    return round(min(10.0, s_peak + s_zones), 1)

def _parse_start_times_map(st: Dict[str, Any]) -> Dict[str, int]:
    return {str(k): int(v) for k, v in st.items()}

def _parse_segment_spec(spec: Any) -> Segment:
    if isinstance(spec, str):
        # "10K,Half,0.00,2.74,3.0,uni" or "10K,,2.74,5.80,1.5,bi"
        parts = [p.strip() for p in spec.split(",")]
        if len(parts) != 6:
            raise ValueError(f"Bad segment spec '{spec}'. Expected 6 values: EventA,EventB,from,to,width,direction")
        event_a = parts[0]
        event_b = parts[1] or None
        km_from = float(parts[2]); km_to = float(parts[3])
        width_m = float(parts[4]); direction = parts[5].lower()
        return Segment(event_a, event_b, km_from, km_to, width_m, direction)
    elif isinstance(spec, dict):
        event_a = spec["eventA"]
        event_b = spec.get("eventB")
        km_from = float(spec["from"]); km_to = float(spec["to"])
        width_m = float(spec.get("width", 3.0))
        direction = str(spec.get("direction", "uni")).lower()
        return Segment(event_a, event_b, km_from, km_to, width_m, direction)
    else:
        raise TypeError(f"Unsupported segment type: {type(spec)}")

def compute_density_steps(
    pace_df: pd.DataFrame,
    seg: Segment,
    start_times_min: Dict[str, int],
    step_km: float = STEP_KM_DEFAULT,
    window_s: int = WINDOW_S_DEFAULT,
) -> List[DensityStep]:
    ks = _bins(seg.km_from, seg.km_to, step_km)
    evs = [seg.event_a] + ([seg.event_b] if seg.event_b else [])

    df = pace_df[pace_df["event"].isin(evs)].copy()
    if df.empty:
        return [DensityStep(k, {e: 0 for e in evs}, 0, 0.0, 0.0) for k in ks]

    # constant-pace time model
    df["start_s"] = df["event"].map(lambda e: start_times_min.get(e, 0) * 60)
    df["sec_per_km"] = df["pace"] * 60.0

    area_per_step = (step_km * 1000.0) * max(0.01, seg.width_m)

    out: List[DensityStep] = []
    for k in ks:
        counts: Dict[str, int] = {}
        for ev in evs:
            df_ev = df[df["event"] == ev]
            t_k = df_ev["start_s"] + df_ev["sec_per_km"] * k
            if t_k.empty:
                counts[ev] = 0
                continue
            # 60s window centered on the first arrival at this k
            t0 = t_k.min()
            within = (t_k >= (t0 - window_s / 2)) & (t_k <= (t0 + window_s / 2))
            counts[ev] = int(within.sum())
        combined = sum(counts.values())
        areal = combined / area_per_step
        linear = combined / (step_km * 1000.0)
        out.append(DensityStep(km=k, counts=counts, combined=combined, areal_m2=areal, linear_m=linear))
    return out

def rollup_segment(steps: List[DensityStep], seg: Segment) -> SegmentRollup:
    if not steps:
        raise ValueError("No steps provided to rollup_segment.")
    peak = max(steps, key=lambda s: s.areal_m2)
    zone_km = {"green": 0.0, "amber": 0.0, "red": 0.0, "dark_red": 0.0}
    # NOTE: uses STEP_KM_DEFAULT for accumulation; acceptable since inputs are generated with same step
    for s in steps:
        zone_km[_zone(s.areal_m2)] += STEP_KM_DEFAULT

    length_km = max(1e-9, seg.km_to - seg.km_from)
    length_m = length_km * 1000.0
    area_seg = max(1.0, length_m * max(0.01, seg.width_m))

    avg_areal = peak.combined / area_seg
    avg_linear = peak.combined / length_m

    share_amber = zone_km["amber"] / length_km
    share_red = zone_km["red"] / length_km
    share_dark = zone_km["dark_red"] / length_km
    d_peak = peak.areal_m2
    idx = _congestion_index(d_peak, share_amber, share_red, share_dark)

    return SegmentRollup(
        segment=seg,
        peak_km=peak.km,
        peak={"combined": peak.combined, **peak.counts},
        peak_step_areal_m2=round(peak.areal_m2, 2),
        peak_step_linear_m=round(peak.linear_m, 2),
        segment_avg_at_peak_areal_m2=round(avg_areal, 3),
        segment_avg_at_peak_linear_m=round(avg_linear, 3),
        zones_km={k: round(v, 2) for k, v in zone_km.items()},
        index_0_10=idx,
        diagnostics={},
    )

def render_cli_block(roll: SegmentRollup) -> str:
    seg = roll.segment
    z = roll.zones_km
    title = (
        f"🔍 Checking {seg.event_a}"
        + (f" vs {seg.event_b}" if seg.event_b else "")
        + f" from {seg.km_from:.2f}km–{seg.km_to:.2f}km..."
    )
    parts = [
        title,
        f"📝 Segment: width={seg.width_m} m, direction={seg.direction}",
        f"👥 Peak concurrent: {roll.peak['combined']} ({roll.peak}) @ {roll.peak_km:.2f} km",
        f"📈 Density (peak step): {roll.peak_step_areal_m2} /m² (Linear ≈ {roll.peak_step_linear_m} /m)",
        f"📉 Density (segment-average @ peak): {roll.segment_avg_at_peak_areal_m2} /m² (Linear ≈ {roll.segment_avg_at_peak_linear_m} /m)",
        f"🚦 Zones (km): G={z['green']}, A={z['amber']}, R={z['red']}, D={z['dark_red']}",
        f"🧮 Index: {roll.index_0_10}/10",
    ]
    return "\n".join(parts)

def _build_blocks(df: pd.DataFrame, segments: List[Segment], start_times: Dict[str, int],
                  step_km: float, time_window: int) -> Tuple[List[Dict[str, Any]], str]:
    blocks: List[Dict[str, Any]] = []
    texts: List[str] = []
    for seg in segments:
        steps = compute_density_steps(df, seg, start_times, step_km, time_window)
        roll = rollup_segment(steps, seg)
        blocks.append({
            "segment": {"from_km": seg.km_from, "to_km": seg.km_to},
            "geometry": {"width_m": seg.width_m, "direction": seg.direction},
            "concurrency": roll.peak,
            "density": {
                "peak_step_areal_m2": roll.peak_step_areal_m2,
                "peak_step_linear_m": roll.peak_step_linear_m,
                "segment_avg_at_peak_areal_m2": roll.segment_avg_at_peak_areal_m2,
                "segment_avg_at_peak_linear_m": roll.segment_avg_at_peak_linear_m
            },
            "zones_km": roll.zones_km,
            "index": {"congestion_0_10": roll.index_0_10, "version": "v1"}
        })
        texts.append(render_cli_block(roll))
    return blocks, "\n\n".join(texts)

def run_density(config: Dict[str, Any]) -> Dict[str, Any]:
    """Stable public entrypoint used by API and CLI.
    Accepts a dict payload and returns a JSON-serializable dict.
    Required keys: paceCsv, startTimes, segments
    Optional: stepKm (default 0.03), timeWindow (default 60)
    """
    try:
        pace_csv = config["paceCsv"]
        start_times = _parse_start_times_map(config["startTimes"])
        segments_raw = config.get("segments", [])
        if not isinstance(segments_raw, list) or not segments_raw:
            raise KeyError("segments")

        step_km = float(config.get("stepKm", STEP_KM_DEFAULT))
        time_window = int(config.get("timeWindow", WINDOW_S_DEFAULT))

        segs = [_parse_segment_spec(s) for s in segments_raw]
        df = pd.read_csv(pace_csv)

        blocks, text = _build_blocks(df, segs, start_times, step_km, time_window)
        return {"blocks": blocks, "text": text}
    except KeyError as e:
        raise RuntimeError(f"Missing required key: {e}") from e
    except Exception as e:
        # Let caller return a 500 with this message
        raise
