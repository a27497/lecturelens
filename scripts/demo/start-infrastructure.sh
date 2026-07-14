#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
[[ -f "$repo_root/.env.demo.local" ]] || { printf 'FAIL Copy .env.demo.example to .env.demo.local first.\n' >&2; exit 1; }
instance="${LECTURELENS_DEMO_INSTANCE:-default}"
[[ "$instance" =~ ^[a-z0-9-]{1,32}$ ]] || { printf 'FAIL LECTURELENS_DEMO_INSTANCE must match [a-z0-9-]{1,32}.\n' >&2; exit 1; }
project_name="lecturelens-demo-$instance"
cd "$repo_root"
compose() { docker compose --project-name "$project_name" --env-file .env.demo.local "$@"; }
wait_healthy() {
  local service="$1" id health
  for _ in $(seq 1 60); do
    id="$(compose ps -q "$service")"
    if [[ -n "$id" ]]; then
      health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$id")"
      [[ "$health" == healthy ]] && return 0
    fi
    sleep 2
  done
  printf 'FAIL %s did not become healthy for %s\n' "$service" "$instance" >&2; return 1
}
wait_completed() {
  local service="$1" id state
  for _ in $(seq 1 60); do
    id="$(compose ps -aq "$service")"
    if [[ -n "$id" ]]; then
      state="$(docker inspect -f '{{.State.Status}}:{{.State.ExitCode}}' "$id")"
      [[ "$state" == exited:0 ]] && return 0
    fi
    sleep 2
  done
  printf 'FAIL %s did not complete for %s\n' "$service" "$instance" >&2; return 1
}
wait_running() {
  local service="$1" id
  for _ in $(seq 1 60); do
    id="$(compose ps -q "$service")"
    [[ -n "$id" && "$(docker inspect -f '{{.State.Status}}' "$id")" == running ]] && return 0
    sleep 2
  done
  printf 'FAIL %s did not become running for %s\n' "$service" "$instance" >&2; return 1
}
compose up -d \
  mysql redis minio minio-init rocketmq-store-init rocketmq-namesrv rocketmq-broker
wait_healthy mysql
wait_healthy redis
wait_healthy minio
wait_completed minio-init
wait_completed rocketmq-store-init
wait_running rocketmq-namesrv
wait_running rocketmq-broker

mq_ready=false
for _ in $(seq 1 40); do
  if compose exec -T rocketmq-broker sh -lc \
    '/home/rocketmq/rocketmq-5.3.4/bin/mqadmin clusterList -n rocketmq-namesrv:9876 >/dev/null 2>&1'; then
    mq_ready=true
    break
  fi
  sleep 3
done
[[ "$mq_ready" == true ]] || { printf 'FAIL RocketMQ broker did not become ready.\n' >&2; exit 1; }
compose exec -T rocketmq-broker sh -lc \
  '/home/rocketmq/rocketmq-5.3.4/bin/mqadmin updateTopic -n rocketmq-namesrv:9876 -c DefaultCluster -t courselingo-analysis-task >/dev/null'
printf 'PASS infrastructure-ready instance=%s project=%s\n' "$instance" "$project_name"
