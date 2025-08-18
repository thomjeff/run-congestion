# Vercel runtime fix

You hit:
```
Error: Function Runtimes must have a valid version, for example `now-php@1.0.0`.
```
This happens when the `functions` runtime key uses an older/invalid value (e.g. `"python3.11"`).  
Newer Vercel CLIs expect **runtime identifiers** in the form `vercel-<language>@<version>`.

## Fix
- Replace your `vercel.json` with the one in this bundle.
- It pins the runtime to **`vercel-python@3.11`** and routes `/api/density` to `api/density.py`.

## vercel.json
```json
{
  "version": 2,
  "functions": {
    "api/density.py": {
      "runtime": "vercel-python@3.11"
    }
  },
  "routes": [
    { "src": "/api/density", "dest": "api/density.py" }
  ]
}
```

## Steps
1) Commit `vercel.json` at the repo root on your `density` branch.
2) Trigger a fresh deploy (any commit, or `vercel --prod`).
3) Smoke test:
   ```bash
   curl -i "https://<your-base>/api/density"
   curl -s -X POST "https://<your-base>/api/density"      -H "Content-Type: application/json" -H "Accept: application/json"      -d '{"paceCsv":"https://raw.githubusercontent.com/thomjeff/run-congestion/main/data/your_pace_data.csv","startTimes":{"10K":440,"Half":460},"segments":[{"eventA":"10K","eventB":"Half","from":0.00,"to":2.74,"width":3.0,"direction":"uni"}],"stepKm":0.03,"timeWindow":60}' | jq
   ```

## Notes
- Keep `requirements.txt` present so Vercel installs dependencies (fastapi, pandas, numpy, etc.).
- Ensure `api/density.py` exports `app = FastAPI(...)` and mounts **`@app.get("/")`** and **`@app.post("/")`** so `/api/density` hits those routes.
