# Vercel Python Runtime — Hard Fix + Triage

You're seeing:
```
Vercel CLI 46.0.2
Error: Function Runtimes must have a valid version, for example `now-php@1.0.0`.
```
This happens when **any** function's runtime value is invalid/missing.

## ✅ Do this (one file, saves a lot of cycles)
Create/replace **vercel.json** at repo root with:
```json
{
  "version": 2,
  "functions": {
    "api/**/*.py": { "runtime": "vercel-python@3.11" }
  },
  "routes": [
    { "src": "/api/density", "dest": "api/density.py" }
  ]
}
```

## 🔍 Then verify (locally before pushing)
```bash
# show every vercel.json in the repo
git ls-files | grep -E 'vercel\.json$' || true

# ensure NO legacy now.json remains
git ls-files | grep -E '(^|/)now\.json$' || true

# list functions that Vercel will see
ls -R api || true
```

If you see **another** `vercel.json` deeper in the tree, remove it. If you see a `now.json`, remove it.

## 🧹 Project-level overrides
Check Vercel Dashboard → **Project → Settings → Functions**:
- If you set Python there, it's OK.
- If there is an **old** runtime value, clear it OR set it to **Python (3.11)** explicitly.

## 🧱 Common blockers
- Another function file with a **bad runtime** in a nested `vercel.json`.
- A leftover **now.json** with `builds`/`functions`.
- A non-Python file under `api/` with no runtime (e.g., `api/index.js`) conflicting with your config.

## 🧪 After deploy: smoke tests
```bash
# Health (requires you added GET "/" in api/density.py)
curl -i "https://<BASE>/api/density"

# POST
curl -s -X POST "https://<BASE>/api/density"   -H "Content-Type: application/json" -H "Accept: application/json"   -d '{"paceCsv":"https://raw.githubusercontent.com/thomjeff/run-congestion/main/data/your_pace_data.csv","startTimes":{"10K":440,"Half":460},"segments":[{"eventA":"10K","eventB":"Half","from":0.00,"to":2.74,"width":3.0,"direction":"uni"}],"stepKm":0.03,"timeWindow":60}' | jq
```
