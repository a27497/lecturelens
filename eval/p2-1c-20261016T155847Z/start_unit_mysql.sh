#!/usr/bin/env bash
# Run only after explicit user approval to start this independent test dependency.
set -euo pipefail
cd /home/dev/projects/lecturelens
python3 - <<'PY'
import importlib.util
from pathlib import Path
p = Path('eval/p2-1c-20261016T155847Z/run_check.py')
spec = importlib.util.spec_from_file_location('p21c_check', p)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
if not module.disk()['allowed']:
    raise SystemExit('DISK_GATE_STOP')
PY
test_name=lecturelens-p21c-unit-mysql-20261017
test_image=sha256:3466ba4a4828aa8d46fb7c3bc16b67b781c98413cf4ea0fac6feaa6e881faa26
docker image inspect "$test_image" --format '{{.Id}}'
if docker container inspect "$test_name" --format '{{.Id}}' >/dev/null 2>&1; then
    echo 'STOP: test container name already exists; no existing container will be changed'
    exit 1
fi
if test -n "$(ss -H -ltn 'sport = :33316')"; then
    echo 'STOP: port 33316 is occupied'
    exit 1
fi
docker run --detach --name "$test_name" --restart=no \
    --label lecturelens.eval=p2-1c-unit \
    --publish 127.0.0.1:33316:3306 --memory=1g --cpus=1 \
    --tmpfs /var/lib/mysql:rw,size=1073741824 \
    --env MYSQL_ALLOW_EMPTY_PASSWORD=yes --env 'MYSQL_ROOT_HOST=%' \
    --env MYSQL_DATABASE=lecturelens_p21c_test \
    "$test_image" --skip-log-bin
for ((attempt=0; attempt<90; attempt++)); do
    if docker exec "$test_name" mysqladmin ping --host=127.0.0.1 --user=root --silent >/dev/null 2>&1; then
        echo 'READY: independent MySQL at 127.0.0.1:33316, lecturelens_p21c_test; no provider configuration'
        exit 0
    fi
    sleep 1
done
echo 'STOP: test database did not become ready; no restart attempted'
exit 1
