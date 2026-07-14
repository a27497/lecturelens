#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
[[ -f "$repo_root/.env.demo.local" ]] || { printf 'FAIL Copy .env.demo.example to .env.demo.local first.\n' >&2; exit 1; }
instance="${LECTURELENS_DEMO_INSTANCE:-default}"
[[ "$instance" =~ ^[a-z0-9-]{1,32}$ ]] || { printf 'FAIL LECTURELENS_DEMO_INSTANCE must match [a-z0-9-]{1,32}.\n' >&2; exit 1; }

cd "$repo_root"
docker compose --project-name "lecturelens-demo-$instance" --env-file .env.demo.local down
printf 'PASS infrastructure-stopped instance=%s volumes-preserved=true\n' "$instance"
