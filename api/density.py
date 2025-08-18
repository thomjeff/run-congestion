#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vercel-compatible FastAPI entrypoint
File: api/density.py
Exports `app` (ASGI) and mounts a POST `/` handler.
Resolved error: `Missing variable handler or app in file "api/density.py"`
"""
from __future__ import annotations
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

import pandas as pd

# Prefer user's compute adapter if present; otherwise fall back to primitives.
_compute_adapter = None
try:
    from density import compute_density as _compute_adapter  # user-provided module
except Exception:
    _compute_adapter = None
    try:
        from run_congestion.density import (
            Segment,
            compute_density_steps,
            rollup_segment,
            render_cli_block,
        )
    except Exception as e:
        # We will raise later inside the request handler with an HTTP 500
        Segment = None  # type: ignore

app = FastAPI(title="run-congestion density API")


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
    parts = [p.strip() for p in spec.split(",")]
    if len(parts) != 6:
        raise HTTPException(
            status_code=400,
            detail=f"Bad segment spec '{spec}'. Expected 6 values: EventA,EventB,from,to,width,direction",
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
    if not isinstance(segments, list) or not segments:
        raise HTTPException(status_code=400, detail="segments must be a non-empty array")
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


def _compute_fallback(pace_csv: str, start_times: Dict[str, int], segments: List[Dict[str, Any]],
                      step_km: float, time_window: int):
    if 'Segment' not in globals() or Segment is None:
        raise RuntimeError("Density primitives not available. Ensure run_congestion.density is deployed.")
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


@app.get("/")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "density"}


@app.post("/")
def density(payload: Dict[str, Any]) -> JSONResponse:
    t0 = time.perf_counter()
    try:
        pace_csv = payload["paceCsv"]
        start_times = _parse_start_times(payload["startTimes"])
        segments = _normalize_segments(payload.get("segments", []))
        step_km = float(payload.get("stepKm", 0.03))
        time_window = int(payload.get("timeWindow", 60))
        verbose = bool(payload.get("verbose", False))  # reserved

        if _compute_adapter is not None:
            result = _compute_adapter(
                paceCsv=pace_csv,
                overlapsCsv=payload.get("overlapsCsv"),
                startTimes=start_times,
                segments=segments,
                stepKm=step_km,
                timeWindow=time_window,
                verbose=verbose,
            )
        else:
            result = _compute_fallback(pace_csv, start_times, segments, step_km, time_window)

        elapsed = time.perf_counter() - t0
        headers = {
            "X-Compute-Seconds": f"{elapsed:.2f}",
            "X-StepKm": f"{step_km:.2f}",
            "X-Events-Seen": ",".join(sorted(start_times.keys())),
        }
        return JSONResponse(content=result, headers=headers)

    except HTTPException:
        raise
    except KeyError as e:
        elapsed = time.perf_counter() - t0
        return JSONResponse(status_code=400, content={"error": f"Missing key: {str(e)}"},
                            headers={"X-Compute-Seconds": f"{elapsed:.2f}"})
    except Exception as e:
        elapsed = time.perf_counter() - t0
        return JSONResponse(status_code=500, content={"error": str(e)},
                            headers={"X-Compute-Seconds": f"{elapsed:.2f}"})
