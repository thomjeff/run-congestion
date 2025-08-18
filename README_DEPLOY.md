# Density API (Vercel) – Production Bundle

This bundle wires your deployed FastAPI endpoint to **your** engine in `run_congestion/density.py`.

## Files
- `api/density.py` — Vercel-ready FastAPI app exporting `app`, with `GET /` (health) and `POST /` (compute). Calls `run_congestion.density.run_density(config)`.
- `run_congestion/__init__.py` — makes the package importable on Vercel.
- `requirements.txt` — ensures `fastapi`, `uvicorn`, `pandas`, `numpy` available.

## Contract expected by the API
Your module **`run_congestion/density.py`** must expose:

```python
def run_density(config: dict) -> dict:
    """Return a JSON-serializable result."""
```

The API will forward payload keys unchanged, e.g.:

```json
{
  "paceCsv": "https://.../your_pace_data.csv",
  "overlapsCsv": "https://.../overlaps.csv",   // optional
  "startTimes": {"Full":420, "10K":440, "Half":460},
  "segments": [
    {"eventA":"10K","eventB":"Half","from":0.00,"to":2.74,"width":3.0,"direction":"uni"}
  ],
  "stepKm": 0.03,
  "timeWindow": 60,
  "verbose": false
}
```

## Deploy
1. Upload these files into your repo (branch `density`), preserving paths.
2. Commit & push to trigger Vercel.
3. Smoke test:

```bash
curl -s "https://<your-base>/api/density" | jq
curl -s -X POST "https://<your-base>/api/density" -H "Content-Type: application/json" -H "Accept: application/json" -d '{
  "paceCsv":"https://raw.githubusercontent.com/thomjeff/run-congestion/main/data/your_pace_data.csv",
  "startTimes":{"Full":420,"10K":440,"Half":460},
  "segments":[{"eventA":"10K","eventB":"Half","from":0.00,"to":2.74,"width":3.0,"direction":"uni"}],
  "stepKm":0.03,"timeWindow":60
}' | jq
```

If you see `{"error":"Density engine import failed: ..."}`, ensure your `run_congestion/density.py` defines `run_density` and that imports succeed on Vercel.
