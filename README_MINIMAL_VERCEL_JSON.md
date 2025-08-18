# Minimal vercel.json (routes-only)

Your build failed because the `functions` block used an invalid runtime slug.
To unblock immediately, remove the `functions` block entirely and let Vercel
auto-detect Python for `api/*.py`.

## Use this `vercel.json` at the repo root:
```json
{
  "version": 2,
  "routes": [
    { "src": "/api/density", "dest": "api/density.py" }
  ]
}
```

## Or simply delete `vercel.json`
If you don't need custom routes, you can delete `vercel.json` completely.
Vercel will map `/api/density` -> `api/density.py` automatically.

## After commit
- Trigger a deploy.
- Test:
  curl -i "https://<base>/api/density"
  curl -s -X POST "https://<base>/api/density" -H "Content-Type: application/json" -d '{"paceCsv":"https://raw.githubusercontent.com/thomjeff/run-congestion/main/data/your_pace_data.csv","startTimes":{"10K":440,"Half":460},"segments":[{"eventA":"10K","eventB":"Half","from":0.00,"to":2.74,"width":3.0,"direction":"uni"}],"stepKm":0.03,"timeWindow":60}'
