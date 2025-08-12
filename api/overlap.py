# api/overlap.py
import json
import os
import time

from run_congestion.cache import LRUCacheTTL
from run_congestion.hashing import fetch_bytes, sha256_bytes, sha256_json
from run_congestion.l2_blob import is_enabled as l2_enabled, get_text as l2_get_text, put_text as l2_put_text

try:
    from run_congestion.bridge import analyze_overlaps
except Exception:
    from run_congestion.engine import analyze_overlaps

L1 = LRUCacheTTL(capacity=int(os.getenv("CACHE_CAPACITY", "64")), ttl_seconds=int(os.getenv("CACHE_TTL", "900")))

def _read_json_body(environ):
    try:
        length = int(environ.get("CONTENT_LENGTH", "0"))
    except ValueError:
        length = 0
    body = environ['wsgi.input'].read(length) if length > 0 else b""
    if not body:
        return {}
    return json.loads(body.decode("utf-8"))

def _response(start_response, status, body, headers=None, content_type="text/plain; charset=utf-8"):
    hdrs = [("Content-Type", content_type)]
    if headers:
        hdrs.extend(headers)
    start_response(status, hdrs)
    return [body.encode("utf-8") if isinstance(body, str) else body]

def app(environ, start_response):
    if environ.get('REQUEST_METHOD') != 'POST':
        return _response(start_response, '405 Method Not Allowed', 'Use POST')
    t0 = time.time()
    try:
        req = _read_json_body(environ)
    except Exception as e:
        return _response(start_response, '400 Bad Request', f'Invalid JSON: {e}')

    pace_src = req.get('paceCsv') or req.get('pace')
    overlaps_src = req.get('overlapsCsv') or req.get('overlaps')
    start_times = req.get('startTimes') or {}
    time_window = int(req.get('timeWindow', 60))
    step_km = float(req.get('stepKm', 0.03))
    rank_by = req.get('rankBy', 'peak_ratio')
    verbose = bool(req.get('verbose', True))
    response_format = req.get('format', 'text')

    if not pace_src or not overlaps_src or not start_times:
        return _response(start_response, '400 Bad Request', 'Missing required fields: paceCsv, overlapsCsv, startTimes')

    try:
        pace_bytes, _ = fetch_bytes(pace_src)
        overlaps_bytes, _ = fetch_bytes(overlaps_src)
    except Exception as e:
        return _response(start_response, '400 Bad Request', f'Failed to load inputs: {e}')

    key_dict = {
        'pace_hash': sha256_bytes(pace_bytes),
        'overlaps_hash': sha256_bytes(overlaps_bytes),
        'start_times': start_times,
        'time_window': time_window,
        'step_km': step_km,
        'rank_by': rank_by,
        'verbose': bool(verbose),
    }
    cache_key = sha256_json(key_dict)

    cached = L1.get(cache_key)
    cache_tier = 'MISS'
    if cached:
        cache_tier = 'L1'
        report_text, summary_records = cached['report_text'], cached['summary']
        compute_ms = cached.get('compute_ms', 0.0)
    else:
        if l2_enabled():
            l2_text = l2_get_text(f"results/{cache_key}.txt")
            l2_json = l2_get_text(f"results/{cache_key}.json")
            if l2_text and l2_json:
                try:
                    summary_records = json.loads(l2_json)
                    report_text = l2_text
                    cache_tier = 'L2'
                    compute_ms = 0.0
                    L1.set(cache_key, {'report_text': report_text, 'summary': summary_records, 'compute_ms': compute_ms})
                except Exception:
                    report_text = None
                    summary_records = None
            else:
                report_text = None
                summary_records = None
        else:
            report_text = None
            summary_records = None

        if report_text is None or summary_records is None:
            result = analyze_overlaps(
                pace_src,
                overlaps_src,
                start_times,
                time_window=time_window,
                step_km=step_km,
                verbose=verbose,
                rank_by=rank_by
            )
            if isinstance(result, tuple) and len(result) >= 2:
                report_text, summary_records = result[0], result[1]
            elif isinstance(result, dict):
                report_text = result.get('reportText', '')
                summary_records = result.get('summary', [])
            else:
                report_text = str(result)
                summary_records = []

            compute_ms = int((time.time() - t0) * 1000)
            L1.set(cache_key, {'report_text': report_text, 'summary': summary_records, 'compute_ms': compute_ms})
            if l2_enabled():
                try:
                    l2_put_text(f"results/{cache_key}.txt", report_text or "")
                    l2_put_text(f"results/{cache_key}.json", json.dumps(summary_records))
                except Exception:
                    pass

    headers = [
        ('X-Overlap-Cache', cache_tier),
        ('X-Compute-Ms', str(compute_ms)),
        ('X-StepKm', str(step_km)),
    ]

    if response_format == 'json':
        body = json.dumps({
            'reportText': report_text,
            'summary': summary_records,
            'cache': {'tier': cache_tier, 'key': cache_key},
        })
        return _response(start_response, '200 OK', body, headers=headers, content_type='application/json; charset=utf-8')

    return _response(start_response, '200 OK', report_text or '')
