#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
export PATH="/opt/node/bin:$HOME/.local/bin:$PATH"
offline=()
for arg in "$@"; do
  if [[ "$arg" == --offline ]]; then offline=(--offline); fi
done
uv sync --project agent-service --locked "${offline[@]}"
exec uv run --project agent-service --no-sync python eval/perf-p0/run.py "$@"
