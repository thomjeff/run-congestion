import io
import os
import tempfile
import pandas as pd
from datetime import datetime
from flask import Request, Response
from run_congestion.bridge import analyze_overlaps

def handler(request: Request) -> Response:
    try:
        body = request.get_json(force=True)

        # Required fields
        pace_csv = body.get("paceCsv")
        overlaps_csv = body.get("overlapsCsv")
        start_times = body.get("startTimes")
        time_window = body.get("timeWindow", 60)
        step_km = body.get("stepKm", 0.1)
        verbose = body.get("verbose", False)
        rank_by = body.get("rankBy", "peak_ratio")
        segments = body.get("segments", [])

        if not pace_csv or not overlaps_csv or not start_times:
            return Response("'paceCsv', 'overlapsCsv', and 'startTimes' are required",
                            status=400)

        # Load overlaps to check available events
        overlaps_df = pd.read_csv(overlaps_csv)
        overlaps_df['event'] = overlaps_df['event'].astype(str).str.strip()
        overlaps_df['overlapswith'] = overlaps_df['overlapswith'].astype(str).str.strip()

        events_seen = sorted(overlaps_df['event'].unique())

        # Segment validation if provided
        if segments:
            bad_segments = []
            valid_events_lower = [e.lower() for e in events_seen]
            seg_rows = []

            for seg in segments:
                try:
                    event_name, dist_range = seg.split(":")
                except ValueError:
                    bad_segments.append(seg)
                    continue

                if event_name.strip().lower() not in valid_events_lower:
                    bad_segments.append(seg)
                    continue

                seg_rows.append(seg)

            if bad_segments:
                return Response(
                    f"Your 'segments' request did not match valid overlaps.\n"
                    f"Requested: {bad_segments}\n"
                    f"Valid events: {', '.join(events_seen)}",
                    status=400
                )

            # Filter overlaps_df for these segments
            filtered = pd.DataFrame()
            for seg in seg_rows:
                event_name, dist_range = seg.split(":")
                start_d, end_d = [float(x) for x in dist_range.split("-")]
                mask = (
                    (overlaps_df['event'].str.lower() == event_name.strip().lower()) &
                    (overlaps_df['start'].round(2) == round(start_d, 2)) &
                    (overlaps_df['end'].round(2) == round(end_d, 2))
                )
                filtered = pd.concat([filtered, overlaps_df[mask]], ignore_index=True)

            if filtered.empty:
                return Response(f"No matching segments found for {segments}", status=400)

            # Write to temp CSV
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
            filtered.to_csv(tmp.name, index=False)
            overlaps_csv = tmp.name

        # Call the main overlap analyzer
        results = analyze_overlaps(
            pace_csv=pace_csv,
            overlaps_csv=overlaps_csv,
            start_times=start_times,
            time_window=time_window,
            step_km=step_km,
            verbose=verbose,
            rank_by=rank_by
        )

        resp = Response(results.to_json(orient="records"),
                        content_type="application/json")
        resp.headers["X-Events-Seen"] = ", ".join(events_seen)
        resp.headers["X-Request-UTC"] = datetime.utcnow().isoformat()
        resp.headers["X-StepKm"] = str(step_km)
        return resp

    except Exception as e:
        return Response(f"Server error: {e}", status=500)