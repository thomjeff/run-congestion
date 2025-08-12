import os, json, tempfile, base64, urllib.request, traceback
from run_congestion.bridge import analyze_overlaps, parse_start_times

def app(environ, start_response):
    try:
        if environ.get("REQUEST_METHOD") != "POST":
            start_response("405 Method Not Allowed", [("Allow", "POST")])
            return [b"Method Not Allowed"]

        try:
            length = int(environ.get("CONTENT_LENGTH", 0))
            raw = environ["wsgi.input"].read(length) if length > 0 else b"{}"
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception as ex:
            start_response("400 Bad Request", [("Content-Type", "text/plain; charset=utf-8")])
            return [f"Invalid JSON: {ex}".encode("utf-8")]

        pace_src     = payload.get("paceCsv")
        overlaps_src = payload.get("overlapsCsv")
        start_times  = payload.get("startTimes")
        time_window  = int(payload.get("timeWindow", 60))
        step_km      = float(payload.get("stepKm", 0.01))
        verbose      = bool(payload.get("verbose", False))
        rank_by      = payload.get("rankBy", "peak_ratio")

        if not (pace_src and overlaps_src and start_times):
            start_response("400 Bad Request", [("Content-Type", "text/plain; charset=utf-8")])
            return [b"Missing required fields: paceCsv, overlapsCsv, startTimes"]

        # Accept either raw URLs or base64-encoded CSV content
        def _fetch_to_tmp(src, suffix):
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            path = tf.name
            try:
                if isinstance(src, str) and src.startswith(("http://","https://")):
                    urllib.request.urlretrieve(src, path)
                else:
                    if isinstance(src, str):
                        data = base64.b64decode(src)
                    else:
                        data = bytes(src)
                    tf.write(data)
            finally:
                tf.close()
            if os.path.getsize(path) == 0:
                raise IOError(f"Input file is empty: {path}")
            return path

        pace_path     = _fetch_to_tmp(pace_src, ".csv")
        overlaps_path = _fetch_to_tmp(overlaps_src, ".csv")

        # Normalize startTimes (list ["Full=420", ...] or dict {"Full":420,...})
        if isinstance(start_times, dict):
            st = {str(k): float(v) for k, v in start_times.items()}
        else:
            st = parse_start_times(start_times)

        report_text, _summary = analyze_overlaps(
            pace_path, overlaps_path, st,
            time_window=time_window, step_km=step_km, verbose=verbose, rank_by=rank_by
        )

        try:
            os.remove(pace_path); os.remove(overlaps_path)
        except OSError:
            pass

        if not report_text.strip():
            report_text = "✅ No overlapping segments detected.\n"

        start_response("200 OK", [("Content-Type", "text/plain; charset=utf-8")])
        return [report_text.encode("utf-8")]

    except Exception:
        tb = traceback.format_exc()
        start_response("500 Internal Server Error", [("Content-Type", "text/plain; charset=utf-8")])
        return [f"Server error:\n{tb}".encode("utf-8")]
