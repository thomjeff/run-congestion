from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import traceback

# Import your logic safely
try:
    from run_congestion.density import run_density
except Exception as e:
    run_density = None

app = FastAPI()

@app.get("/api/density")
async def health():
    return {"status": "ok", "service": "density"}

@app.post("/api/density")
async def density(request: Request):
    try:
        body = await request.json()
        if run_density is None:
            raise RuntimeError("Failed to import run_density; check run_congestion package.")
        result = run_density(body)
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e), "trace": traceback.format_exc()})
