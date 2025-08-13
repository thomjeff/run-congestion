#!/usr/bin/env bash
set -euo pipefail

# --- load .env if present ----------------------------------------------------
ENV_FILE="${ENV_FILE:-.env}"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

# --- defaults (can be overridden by .env) ------------------------------------
API_URL="${API_URL:-}"
PACE_CSV_URL="${PACE_CSV_URL:-https://raw.githubusercontent.com/thomjeff/run-congestion/main/data/your_pace_data.csv}"
OVERLAPS_CSV_URL="${OVERLAPS_CSV_URL:-https://raw.githubusercontent.com/thomjeff/run-congestion/main/data/overlaps.csv}"
LOCAL_PACE_CSV="${LOCAL_PACE_CSV:-data/your_pace_data.csv}"
LOCAL_OVERLAPS_CSV="${LOCAL_OVERLAPS_CSV:-data/overlaps.csv}"
START_TIMES_JSON="${START_TIMES_JSON:-{\"Full\":420,\"10K\":440,\"Half\":460}}"
TIME_WINDOW="${TIME_WINDOW:-60}"
STEP_KM="${STEP_KM:-0.03}"
RANK_BY="${RANK_BY:-peak_ratio}"
VERBOSE="${VERBOSE:-true}"
CURL_BIN="${CURL_BIN:-curl}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

OUT_DIR="${OUT_DIR:-results/test_runs}"
mkdir -p "$OUT_DIR"

usage() {
  cat <<USAGE
Usage: $0 <CASE_ID|all|list> [--dry-run]

CASE_IDs:
  CLI:
    C1  All segments, verbose, export
    C2  Subset segments (valid)
    C3  Rank by intensity
    C4  Minimal run (quiet)
    C5  Bad request: missing overlaps arg
    C6  Bad segment spec
    C7  Back-compat alias --step

  API:
    A1  All segments
    A2  Subset segments (valid)
    A3  Rank by intensity
    A4  Bad request: missing required field
    A5  Bad segments (invalid)
    A6  Step size alias step_km
    A7  JSON parse error
    A8  Performance header present

Examples:
  $0 list
  $0 C1
  $0 A2
  $0 all
Env via .env or environment:
  API_URL, PACE_CSV_URL, OVERLAPS_CSV_URL, LOCAL_PACE_CSV, LOCAL_OVERLAPS_CSV,
  START_TIMES_JSON, TIME_WINDOW, STEP_KM, RANK_BY, VERBOSE
USAGE
}

DRY_RUN=0
if [[ "${2:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

if [[ "${1:-}" == "" ]]; then
  usage; exit 1
fi

list_cases() {
  usage
}

log_and_run() {
  local name="$1"; shift
  local cmd="$*"
  local ts
  ts="$(date -u +%Y-%m-%dT%H%M%S)"
  local log="${OUT_DIR}/${ts}_${name}.log"
  echo "▶ ${name}"
  echo "\$ $cmd"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] skipped execution"
    return 0
  fi
  # run and tee
  ( eval "$cmd" ) | tee "$log"
  echo "✔ wrote log: $log"
}

# --- CASES -------------------------------------------------------------------

run_C1() {
  log_and_run "C1_cli_all_segments" \
  "$PYTHON_BIN -m run_congestion.cli_run_and_export \
    $LOCAL_PACE_CSV \
    $LOCAL_OVERLAPS_CSV \
    --start-times Full=420 10K=440 Half=460 \
    --time-window $TIME_WINDOW \
    --step-km $STEP_KM \
    --verbose \
    --export-summary summary.csv"
}

run_C2() {
  log_and_run "C2_cli_subset_segments" \
  "$PYTHON_BIN -m run_congestion.cli_run_and_export \
    $LOCAL_PACE_CSV $LOCAL_OVERLAPS_CSV \
    --start-times Full=420 10K=440 Half=460 \
    --time-window $TIME_WINDOW \
    --step-km $STEP_KM \
    --verbose \
    --segments \"10K:5.81-8.10\" \"Full:29.03-37.00\""
}

run_C3() {
  log_and_run "C3_cli_rank_intensity" \
  "$PYTHON_BIN -m run_congestion.cli_run_and_export \
    $LOCAL_PACE_CSV $LOCAL_OVERLAPS_CSV \
    --start-times Full=420 10K=440 Half=460 \
    --time-window $TIME_WINDOW \
    --step-km $STEP_KM \
    --rank-by intensity"
}

run_C4() {
  log_and_run "C4_cli_minimal_quiet" \
  "$PYTHON_BIN -m run_congestion.cli_run_and_export \
    $LOCAL_PACE_CSV $LOCAL_OVERLAPS_CSV \
    --start-times Full=420 10K=440 Half=460 \
    --time-window $TIME_WINDOW \
    --step-km $STEP_KM"
}

run_C5() {
  # expect argparse failure
  log_and_run "C5_cli_missing_arg" \
  "$PYTHON_BIN -m run_congestion.cli_run_and_export \
    $LOCAL_PACE_CSV \
    --start-times Full=420 10K=440 Half=460 || true"
}

run_C6() {
  log_and_run "C6_cli_bad_segment" \
  "$PYTHON_BIN -m run_congestion.cli_run_and_export \
    $LOCAL_PACE_CSV $LOCAL_OVERLAPS_CSV \
    --start-times Full=420 10K=440 Half=460 \
    --segments \"Full:99.00-100.00\" || true"
}

run_C7() {
  log_and_run "C7_cli_step_alias" \
  "$PYTHON_BIN -m run_congestion.cli_run_and_export \
    $LOCAL_PACE_CSV $LOCAL_OVERLAPS_CSV \
    --start-times Full=420 10K=440 Half=460 \
    --time-window $TIME_WINDOW \
    --step $STEP_KM \
    --verbose"
}

api_post() {
  local json="$1"
  if [[ -z "${API_URL}" ]]; then
    echo "ERROR: API_URL is not set. Put it in .env or export it." >&2
    exit 2
  fi
  $CURL_BIN -s -D - -X POST "$API_URL" \
    -H "Content-Type: application/json" \
    -d "$json"
}

run_A1() {
  local payload
  payload=$(cat <<JSON
{"paceCsv":"$PACE_CSV_URL","overlapsCsv":"$OVERLAPS_CSV_URL","startTimes":$START_TIMES_JSON,"timeWindow":$TIME_WINDOW,"stepKm":$STEP_KM,"verbose":true,"rankBy":"$RANK_BY"}
JSON
)
  log_and_run "A1_api_all_segments" "api_post '$payload'"
}

run_A2() {
  local payload
  payload=$(cat <<JSON
{"paceCsv":"$PACE_CSV_URL","overlapsCsv":"$OVERLAPS_CSV_URL","startTimes":$START_TIMES_JSON,"timeWindow":$TIME_WINDOW,"stepKm":$STEP_KM,"verbose":true,"rankBy":"$RANK_BY","segments":["10K:5.81-8.10","Full:29.03-37.00"]}
JSON
)
  log_and_run "A2_api_subset_segments" "api_post '$payload'"
}

run_A3() {
  local payload
  payload=$(cat <<JSON
{"paceCsv":"$PACE_CSV_URL","overlapsCsv":"$OVERLAPS_CSV_URL","startTimes":$START_TIMES_JSON,"timeWindow":$TIME_WINDOW,"stepKm":$STEP_KM,"verbose":false,"rankBy":"intensity"}
JSON
)
  log_and_run "A3_api_rank_intensity" "api_post '$payload'"
}

run_A4() {
  local payload
  payload='{"overlapsCsv":"'"$OVERLAPS_CSV_URL"'","startTimes":'"$START_TIMES_JSON"'}'
  log_and_run "A4_api_missing_pace" "api_post '$payload' || true"
}

run_A5() {
  local payload
  payload='{"paceCsv":"'"$PACE_CSV_URL"'","overlapsCsv":"'"$OVERLAPS_CSV_URL"'","startTimes":'"$START_TIMES_JSON"',"segments":["Full:99.00-100.00"]}'
  log_and_run "A5_api_bad_segments" "api_post '$payload' || true"
}

run_A6() {
  local payload
  payload='{"paceCsv":"'"$PACE_CSV_URL"'","overlapsCsv":"'"$OVERLAPS_CSV_URL"'","startTimes":'"$START_TIMES_JSON"',"timeWindow":'"$TIME_WINDOW"',"step_km":'"$STEP_KM"',"verbose":true}'
  log_and_run "A6_api_step_alias" "api_post '$payload'"
}

run_A7() {
  local payload
  payload='{"paceCsv":"'"$PACE_CSV_URL"'","overlapsCsv":"'"$OVERLAPS_CSV_URL"'","startTimes":'"$START_TIMES_JSON"'\n BROKEN'
  log_and_run "A7_api_json_error" "api_post '$payload' || true"
}

run_A8() {
  local payload
  payload='{"paceCsv":"'"$PACE_CSV_URL"'","overlapsCsv":"'"$OVERLAPS_CSV_URL"'","startTimes":'"$START_TIMES_JSON"',"timeWindow":'"$TIME_WINDOW"',"stepKm":'"$STEP_KM"',"verbose":false}'
  log_and_run "A8_api_perf_header" "api_post '$payload'"
}

run_case() {
  case "$1" in
    list) list_cases ;;
    all) for id in C1 C2 C3 C4 C5 C6 C7 A1 A2 A3 A4 A5 A6 A7 A8; do run_case "$id"; done ;;
    C1|C2|C3|C4|C5|C6|C7|A1|A2|A3|A4|A5|A6|A7|A8) "run_$1" ;;
    *) echo "Unknown case: $1"; usage; exit 1 ;;
  esac
}

run_case "$1"
