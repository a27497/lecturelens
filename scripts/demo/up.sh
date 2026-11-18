#!/usr/bin/env bash
# One command from a clean clone to a browsable demo course. Mock mode by default.
set -euo pipefail
exec python3 "$(dirname "${BASH_SOURCE[0]}")/stack.py" up "$@"
