#!/usr/bin/env bash
# Stops the demo stack started by up.sh; add --purge to delete its volumes and state.
set -euo pipefail
exec python3 "$(dirname "${BASH_SOURCE[0]}")/stack.py" down "$@"
