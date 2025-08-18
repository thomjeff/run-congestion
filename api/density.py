from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional
import pandas as pd

STEP_KM = 0.03
WINDOW_S = 60

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

def _bins(k0: float, k1: float, step_km: float = STEP_KM) -> List[float]:
    n = int(round((k1 - k0) / step_km))
    return [round(k0 + i*step_km, 2) for i in range(n+1)]

def _zone(density: float) -> str:
    if density < 1.0:  return "green"
    if density < 1.5:  return "amber"
    if density < 2.0:  return "red"
    return "dark_red"

def _congestion_index(d_peak: float, share_amber: float, share_red: float, share_dark: float) -> float:
    if d_peak < 1.0:       s_peak = 0.0
    elif d_peak < 1.5:     s_peak = 2.0 * (d_peak - 1.0) / 0.5
    elif d_peak < 2.0:     s_peak = 2.0 + 2.0 * (d_peak - 1.5) / 0.5
    else:                  s_peak = 4.0 + 1.0 * (min(d_peak, 3.0) - 2.0) / 1.0
    s_peak = max(0.0, min(5.0, s_peak))
    s_zones = 3.0 * min(1.0, 0.4*share_amber + 0.8*share_red + 1.0*share_dark)
    return round(min(10.0, s_peak + s_zones), 1)

def compute_density_steps(
    pace_df: pd.DataFrame,
    seg: Segment,
    start_times_min: Dict[str, int],
    step_km: float = STEP_KM,
    window_s: int = WINDOW_S,
) -> List[DensityStep]:
    ks = _bins(seg.km_from, seg.km_to, step_km)
    evs = [seg.event_a] + ([seg.event_b] if seg.event_b else [])

    df = pace_df[pace_df['event'].isin(evs)].copy()
    if df.empty:
        return [DensityStep(k, {e:0 for e in evs}, 0, 0.0, 0.0) for k in ks]

    df['start_s'] = df['event'].map(lambda e: start_times_min.get(e, 0)*60)
    df['sec_per_km'] = df['pace'] * 60.0

    area_per_step = (step_km * 1000.0) * max(0.01, seg.width_m)

    out: List[DensityStep] = []
    for k in ks:
        counts = {}
        for ev in evs:
            df_ev = df[df['event'] == ev]
            t_k = df_ev['start_s'] + df_ev['sec_per_km'] * k
            if t_k.empty:
                counts[ev] = 0
                continue
            t0 = t_k.min()
            within = (t_k >= (t0 - window_s/2)) & (t_k <= (t0 + window_s/2))
            counts[ev] = int(within.sum())
        combined = sum(counts.values())
        areal = combined / area_per_step
        linear = combined / (step_km * 1000.0)
        out.append(DensityStep(km=k, counts=counts, combined=combined, areal_m2=areal, linear_m=linear))
    return out

def rollup_segment(steps: List[DensityStep], seg: Segment) -> SegmentRollup:
    if not steps:
        raise ValueError('No steps provided to rollup_segment.')
    peak = max(steps, key=lambda s: s.areal_m2)
    zone_km = {'green':0.0,'amber':0.0,'red':0.0,'dark_red':0.0}
    for s in steps:
        zone_km[_zone(s.areal_m2)] += STEP_KM

    length_km = seg.km_to - seg.km_from
    length_m  = max(1.0, length_km * 1000.0)
    area_seg  = max(1.0, length_m * seg.width_m)

    avg_areal  = peak.combined / area_seg
    avg_linear = peak.combined / length_m

    share_amber = zone_km['amber'] / max(1e-9, length_km)
    share_red   = zone_km['red']   / max(1e-9, length_km)
    share_dark  = zone_km['dark_red'] / max(1e-9, length_km)
    d_peak      = peak.areal_m2

    idx = _congestion_index(d_peak, share_amber, share_red, share_dark)

    return SegmentRollup(
        segment=seg,
        peak_km=peak.km,
        peak={'combined': peak.combined, **peak.counts},
        peak_step_areal_m2=round(peak.areal_m2, 2),
        peak_step_linear_m=round(peak.linear_m, 2),
        segment_avg_at_peak_areal_m2=round(avg_areal, 3),
        segment_avg_at_peak_linear_m=round(avg_linear, 3),
        zones_km={k: round(v, 2) for k,v in zone_km.items()},
        index_0_10=idx,
        diagnostics={}
    )

def render_cli_block(roll: SegmentRollup) -> str:
    seg = roll.segment
    z = roll.zones_km
    # Avoid backslash line continuation; use parentheses for clean concatenation.
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
