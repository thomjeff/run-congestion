#!/usr/bin/env python3
# FastAPI app for Vercel: file must export `app`
from __future__ import annotations
import time
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

# Import user's production density engine
try:
    from run_congestion.density import run_density  # must accept a dict and return JSON-serializable
except Exception as e:
    run_density = None
    _import_err = e

app = FastAPI(title="run-congestion density API")

@app.get("/")
async def health() -> Dict[str, str]:
    return {"status": "ok", "service": "density"}

def _ensure_fields(payload: Dict[str, Any], fields: List[str]):
    for f in fields:
        if f not in payload:
            raise HTTPException(status_code=400, detail=f"Missing required field: {f}")

@app.post("/")
async def density(request: Request):
    t0 = time.perf_counter()
    try:
        payload = await request.json()
        if run_density is None:
            raise RuntimeError(f"Density engine import failed: {_import_err!r}. Ensure run_congestion/density.py defines run_density(config: dict).")

        # Required fields
        _ensure_fields(payload, ["paceCsv", "startTimes", "segments"])

        # Pass through as-is; engine is responsible for semantics
        result = run_density(payload)

        elapsed = time.perf_counter() - t0
        headers = {"X-Compute-Seconds": f"{elapsed:.2f}"}
        # Ensure serializable
        return JSONResponse(content=result, headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        elapsed = time.perf_counter() - t0
        return JSONResponse(status_code=500, content={"error": str(e)}, headers={"X-Compute-Seconds": f"{elapsed:.2f}"})