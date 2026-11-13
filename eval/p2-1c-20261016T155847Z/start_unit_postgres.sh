#!/usr/bin/env bash
# Prepared only: starting this dependency requires separate explicit user approval.
set -euo pipefail
cd /home/dev/projects/lecturelens
python3 - <<'PY'
import importlib.util
from pathlib import Path
p=Path('eval/p2-1c-20261016T155847Z/run_check.py')
spec=importlib.util.spec_from_file_location('checks',p)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
if not module.disk()['allowed']:
    raise SystemExit('DISK_GATE_STOP')
PY
test_name=lecturelens-p21c-unit-postgres-20261017
test_image=sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f
docker image inspect "$test_image" --format '{{.Id}}'
if docker container inspect "$test_name" --format '{{.Id}}' >/dev/null 2>&1; then
    echo 'STOP: test container name already exists; no existing container changed'
    exit 1
fi
if test -n "$(ss -H -ltn 'sport = :33317')"; then
    echo 'STOP: port 33317 is occupied'
    exit 1
fi
docker run --detach --name "$test_name" --restart=no \
    --label lecturelens.eval=p2-1c-unit-postgres \
    --publish 127.0.0.1:33317:5432 --memory=1g --cpus=1 \
    --tmpfs /var/lib/postgresql/data:rw,size=1073741824 \
    --env POSTGRES_HOST_AUTH_METHOD=trust --env POSTGRES_USER=lecturelens \
    --env POSTGRES_DB=lecturelens_agent_test "$test_image"
for ((attempt=0; attempt<90; attempt++)); do
    if docker exec "$test_name" pg_isready --host=127.0.0.1 --username=lecturelens --dbname=lecturelens_agent_test >/dev/null 2>&1; then
        echo 'READY: independent PostgreSQL at 127.0.0.1:33317, lecturelens_agent_test'
        exit 0
    fi
    sleep 1
done
echo 'STOP: test database did not become ready; no restart attempted'
exit 1
