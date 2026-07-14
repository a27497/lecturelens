#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
env_file="${1:-$repo_root/.env.demo.local}"
[[ -f "$env_file" ]] || { printf 'FAIL Copy .env.demo.example to .env.demo.local first.\n' >&2; exit 1; }

while IFS= read -r line || [[ -n "$line" ]]; do
  line="${line%$'\r'}"
  [[ -z "$line" || "$line" == \#* ]] && continue
  [[ "$line" == *=* ]] || { printf 'FAIL Invalid Demo environment entry.\n' >&2; exit 1; }
  key="${line%%=*}"; value="${line#*=}"
  [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || { printf 'FAIL Invalid Demo environment variable name.\n' >&2; exit 1; }
  export "$key=$value"
done < "$env_file"

if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:8080 -sTCP:LISTEN >/dev/null 2>&1; then
  printf 'FAIL Port 8080 is already in use; this script will not stop an unknown process.\n' >&2
  exit 1
fi

cd "$repo_root/backend"
exec ./mvnw spring-boot:run
