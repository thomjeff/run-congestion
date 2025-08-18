# api/density.py — Vercel-compatible FastAPI app exporting `app`
from __future__ import annotations
import time
from typing import Any, Dict, List
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="run-congestion density API")

# Import engine
try:
    from run_congestion.density import run_density  # def run_density(config: dict) -> dict
except Exception as _e:
    run_density = None
    _import_err = _e

@app.get("/")
async def health() -> Dict[str, str]:
    return {"status": "ok", "service": "density"}

def _require(payload: Dict[str, Any], fields: List[str]) -> None:
    missing = [f for f in fields if f not in payload]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing)}")

@app.post("/")
async def compute(request: Request):
    t0 = time.perf_counter()
    try:
        if run_density is None:
            raise RuntimeError(
                f"Density engine import failed: {_import_err!r}. "
                "Ensure run_congestion/density.py defines run_density(config: dict)."
            )
        payload = await request.json()
        _require(payload, ["paceCsv", "startTimes", "segments"])
        result = run_density(payload)
        elapsed = time.perf_counter() - t0
        return JSONResponse(content=result, headers={"X-Compute-Seconds": f"{elapsed:.2f}"})
    except HTTPException:
        raise
    except Exception as e:
        elapsed = time.perf_counter() - t0
        return JSONResponse(status_code=500, content={"error": str(e)}, headers={"X-Compute-Seconds": f"{elapsed:.2f}"})
