import json
import os
from run_congestion.engine import analyze_overlaps, parse_start_times

def handler(request, response):
    try:
        # Expect JSON body with required params
        body = request.get_json()
        pace_data_file = body.get("pace_data_file", "data/your_pace_data.csv")
        overlaps_file = body.get("overlaps_file", "data/overlaps.csv")
        start_times_str = body.get("start_times")
        time_window = int(body.get("time_window", 60))
        step = float(body.get("step", 0.01))
        verbose = bool(body.get("verbose", False))

        start_times = parse_start_times(start_times_str)
        results_text = analyze_overlaps(
            pace_data_file,
            overlaps_file,
            start_times,
            time_window,
            step,
            verbose
        )

        return response.json({"status": "success", "output": results_text})

    except Exception as e:
        return response.status(500).json({"status": "error", "message": str(e)})