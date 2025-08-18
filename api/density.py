#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""api/density.py
FastAPI endpoint exposing density-based congestion analysis.

POST /api/density
Payload:
{
  "paceCsv": "<url-or-path-to-your_pace_data.csv>",
  "overlapsCsv": "<optional, retained for compatibility>",
  "startTimes": {"Full":420, "10K":440, "Half":460},
  "segments": [
      // Either a string spec...
      "10K,Half,0.00,2.74,3.0,uni",
      "10K,,2.74,5.80,1.5,bi",
      // ...or an object form:
      {"eventA":"10K","eventB":"Half","from":0.00,"to":2.74,"width":3.0,"direction":"uni"}
  ],
  "stepKm": 0.03,       // optional, default 0.03
  "timeWindow": 60,     // optional, default 60 (seconds)
  "verbose": false      // optional
}

Response:
- JSON payload (application/json) with `blocks` (structured) and `text` (CLI-style)
- Headers include X-Compute-Seconds and other diagnostics
"""

from __future__ import annotations
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

import pandas as pd

# Try both import paths to be flexible with repo layouts
_compute_adapter = None
try:
    # Preferred: your dedicated density engine module (user-provided)
    from density import compute_density as _compute_adapter  # type: ignore
except Exception:
    try:
        # Fallback: our run_congestion.density primitives
        from run_congestion.density import (
            Segment,
            compute_density_steps,
            rollup_segment,
            render_cli_block,
        )
    except Exception as e:
        raise RuntimeError(
            "No density engine found. Ensure either `density.compute_density` or `run_congestion.density` is available."
        ) from e

router = APIRouter()


def _parse_start_times(obj: Dict[str, Any]) -> Dict[str, int]:
    if not isinstance(obj, dict) or not obj:
        raise HTTPException(status_code=400, detail="startTimes must be a non-empty object of minutes by event")
    out: Dict[str, int] = {}
    for k, v in obj.items():
        try:
            out[str(k)] = int(v)
        except Exception:
            raise HTTPException(status_code=400, detail=f"startTimes['{k}'] must be an integer (minutes)")
    return out


def _parse_segment_str(spec: str) -> Dict[str, Any]:
    # "10K,Half,0.00,2.74,3.0,uni" or "10K,,2.74,5.80,1.5,bi"
    parts = [p.strip() for p in spec.split(",")]
    if len(parts) != 6:
        raise HTTPException(
            status_code=400,
            detail=f"Bad segment spec '{spec}'. Expected 6 values: EventA,EventB,from,to,width,direction"
        )
    eventA = parts[0]
    eventB = parts[1] or None
    try:
        k_from = float(parts[2]); k_to = float(parts[3])
        width = float(parts[4])
        direction = parts[5].lower()
        if direction not in ("uni", "bi"):
            raise ValueError("direction must be 'uni' or 'bi'")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid numeric/direction in segment '{spec}': {e}")
    return {"eventA": eventA, "eventB": eventB, "from": k_from, "to": k_to, "width": width, "direction": direction}


def _normalize_segments(segments: List[Any]) -> List[Dict[str, Any]]:
    norm: List[Dict[str, Any]] = []
    for s in segments:
        if isinstance(s, str):
            norm.append(_parse_segment_str(s))
        elif isinstance(s, dict):
            required = ["eventA", "from", "to"]
            for r in required:
                if r not in s:
                    raise HTTPException(status_code=400, detail=f"segment object missing '{r}'")
            norm.append({
                "eventA": s["eventA"],
                "eventB": s.get("eventB"),
                "from": float(s["from"]),
                "to": float(s["to"]),
                "width": float(s.get("width", 3.0)),
                "direction": str(s.get("direction", "uni")).lower()
            })
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported segment type: {type(s)}")
    return norm


def _run_adapter_compute(pace_csv: str, overlaps_csv: Optional[str], start_times: Dict[str, int],
                         segments: List[Dict[str, Any]], step_km: float, time_window: int, verbose: bool):
    """If the user has `density.compute_density`, use it; otherwise synthesize via run_congestion.density."""
    if _compute_adapter is not None:
        # Expect a function that accepts these arguments, return JSON-like dict
        return _compute_adapter(
            paceCsv=pace_csv,
            overlapsCsv=overlaps_csv,
            startTimes=start_times,
            segments=segments,
            stepKm=step_km,
            timeWindow=time_window,
            verbose=verbose,
        )
    else:
        # Build equivalent with primitives
        from run_congestion.density import Segment, compute_density_steps, rollup_segment, render_cli_block
        df = pd.read_csv(pace_csv)
        blocks = []
        texts = []
        for s in segments:
            seg = Segment(
                event_a=s["eventA"],
                event_b=s.get("eventB"),
                km_from=s["from"],
                km_to=s["to"],
                width_m=s.get("width", 3.0),
                direction=s.get("direction", "uni"),
            )
            steps = compute_density_steps(df, seg, start_times, step_km, time_window)
            roll = rollup_segment(steps, seg)
            # structure
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
        return {"blocks": blocks, "text": "\n\n".join(texts)}


@router.post("/density")
def density(payload: Dict[str, Any]) -> JSONResponse:
    t0 = time.perf_counter()

    try:
        pace_csv = payload["paceCsv"]
        overlaps_csv = payload.get("overlapsCsv")  # kept for compatibility; not required
        start_times = _parse_start_times(payload["startTimes"])
        segments_raw = payload.get("segments", [])
        if not isinstance(segments_raw, list) or not segments_raw:
            raise HTTPException(status_code=400, detail="segments must be a non-empty array")
        segments = _normalize_segments(segments_raw)
        step_km = float(payload.get("stepKm", 0.03))
        time_window = int(payload.get("timeWindow", 60))
        verbose = bool(payload.get("verbose", False))

        result = _run_adapter_compute(
            pace_csv=pace_csv,
            overlaps_csv=overlaps_csv,
            start_times=start_times,
            segments=segments,
            step_km=step_km,
            time_window=time_window,
            verbose=verbose,
        )

        elapsed = time.perf_counter() - t0
        headers = {
            "X-Compute-Seconds": f"{elapsed:.2f}",
            "X-StepKm": f"{step_km:.2f}",
            "X-Events-Seen": ",".join(sorted(start_times.keys())),
        }
        # Ensure consistent JSON shape
        if "blocks" not in result:
            # assume adapter returned dict keyed by segments; normalize lightly
            result = {"blocks": result, "text": ""}
        return JSONResponse(content=result, headers=headers)

    except HTTPException:
        raise
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing key: {e}")
    except Exception as e:
        elapsed = time.perf_counter() - t0
        headers = {"X-Compute-Seconds": f"{elapsed:.2f}"}
        raise HTTPException(status_code=500, detail=str(e))

