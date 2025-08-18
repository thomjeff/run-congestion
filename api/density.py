
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

app = FastAPI(title="run-congestion density API", version="0.1.0")

class Segment(BaseModel):
    eventA: str = Field(..., description="Primary event label")
    eventB: Optional[str] = Field(None, description="Secondary event label (if overlap)")
    from_: float = Field(..., alias="from", description="Segment start km")
    to: float = Field(..., description="Segment end km")
    width: float = Field(..., description="Trail width (m)")
    direction: str = Field(..., description="uni|bi")

class DensityRequest(BaseModel):
    paceCsv: str
    startTimes: Dict[str, float]
    segments: List[Segment]
    stepKm: float = 0.03
    timeWindow: int = 60

@app.get("/health")
def health():
    return {"ok": True, "service": "density", "version": "0.1.0"}

@app.post("/")
def run_density(req: DensityRequest):
    # For now we just echo back a normalized payload so callers can verify wiring.
    # This avoids 404s and proves the route exists. Real computation can be added behind this.
    return {
        "echo": {
            "paceCsv": req.paceCsv,
            "startTimes": req.startTimes,
            "segments": [s.model_dump(by_alias=True) for s in req.segments],
            "stepKm": req.stepKm,
            "timeWindow": req.timeWindow,
        }
    }

# Vercel needs the module-level "app" object; the POST path is "/" because the function is mounted at /api/density
