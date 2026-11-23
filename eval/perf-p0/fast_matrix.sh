#!/usr/bin/env bash
# Full L2 matrix; all timed groups remain sequential on the entire rental host.
set -euo pipefail
umask 077
cd "$(dirname "$0")/../.."

usage() {
  echo "Usage: bash eval/perf-p0/fast_matrix.sh NEW_OUTPUT EXPIRY_UTC [--include-s2] [--offline-bootstrap] [--build-minio]" >&2
  echo "Rental host only. --include-s2 selects the approved eval-only QA limit of 100000/min." >&2
  exit 2
}
[[ $# -ge 2 ]] || usage
output=$1
expiry=$2
shift 2
s2=0
bootstrap=()
minio=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --include-s2) s2=1 ;;
    --offline-bootstrap) bootstrap=(--offline) ;;
    --build-minio) minio=(--build-minio) ;;
    *) usage ;;
  esac
  shift
done

# Refuse another automatic matrix in this checkout; do not overlap manual loads.
mkdir -p .data
exec 9>.data/l2b-fast.lock
flock -n 9 || { echo "An L2b matrix already owns this checkout." >&2; exit 1; }
mkdir -m 700 -- "$output"
output=$(cd "$output" && pwd)
seed="$output/shakedown"
sha=$(git rev-parse HEAD)
SECONDS=0
cap=28800
expires=$(date -u -d "$expiry" +%s)
remaining=$(( expires - $(date -u +%s) ))
if (( remaining < cap )); then cap=$remaining; fi

check_budget() {
  # Per-invocation deadline, 600s cleanup margin, 900s final export reserve.
  if (( SECONDS + $1 + 600 + 900 > cap )); then
    echo "Stop: insufficient time under the 8-hour cap. Remaining points are NOT_RUN." >&2
    exit 1
  fi
}

check_budget 1800
scenarios=S1,S3,S4
qa=10
if (( s2 )); then scenarios=S1,S2,S3,S4; qa=100000; fi
python3 scripts/dev/run_check.py --name l2-shakedown --output "$output/checks" --timeout 2400 -- \
  bash eval/perf-p0/run.sh "${bootstrap[@]}" "${minio[@]}" --profile rental \
  --scenarios "$scenarios" --concurrency 1 --requests 3 --timeout 60 \
  --mock-delay-ms 150 --qa-per-minute "$qa" --retrieval-concurrency 4 --run-concurrency 2 \
  --run-deadline 1800 --output "$seed"
agent-service/.venv/bin/python eval/perf-p0/verify.py "$seed" --sha "$sha" --check-inputs

run_point() {
  local name=$1 scenarios=$2 retrieval=$3 lanes=$4 qa=$5
  check_budget 3000
  python3 scripts/dev/run_check.py --name "l2-$name-r$rep" --output "$output/checks" --timeout 3600 -- \
    bash eval/perf-p0/run.sh --offline "${minio[@]}" --reuse-build-from "$seed" --profile rental \
    --scenarios "$scenarios" --concurrency 1,4,8,16 --seconds 60 --timeout 60 \
    --mock-delay-ms 150 --qa-per-minute "$qa" --retrieval-concurrency "$retrieval" \
    --run-concurrency "$lanes" --run-deadline 3000 --output "$output/$name-r$rep"
  agent-service/.venv/bin/python eval/perf-p0/verify.py "$output/$name-r$rep" --sha "$sha" --check-inputs
  agent-service/.venv/bin/python - "$output/$name-r$rep/result.json" "$seed/result.json" <<'PY'
import json
import sys
from pathlib import Path

r = json.loads(Path(sys.argv[1]).read_text())
seed = json.loads(Path(sys.argv[2]).read_text())
for key in ("docker_image_ids", "python_distributions", "java_version", "javac_version"):
    if r[key] != seed[key]:
        raise SystemExit(f"Stop: {key} changed since shakedown; comparison is ineligible.")
wall = sum(g["wall_seconds"] for g in r["groups"])
print(f"Observed invocation: {r['elapsed_seconds'] / 60:.1f} min; "
      f"measured windows/drain: {wall / 60:.1f} min; "
      f"remaining overhead: {(r['elapsed_seconds'] - wall) / 60:.1f} min.", flush=True)
PY
}

for rep in 1 2 3; do
  if (( s2 )); then
    run_point a-qa S1,S2,S3 4 2 100000
  else
    run_point a-qa S1,S3 4 2 10
  fi
  run_point a-run S4 4 2 10
  if (( s2 )); then
    run_point b-qa S1,S2 8 2 100000
  else
    run_point b-qa S1 8 2 10
  fi
  run_point c-run S4 4 4 10
done
echo "Core matrix verified. Export evidence (including shakedown), then release the rental within the cap."
