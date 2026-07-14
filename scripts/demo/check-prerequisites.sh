#!/usr/bin/env bash
set -u

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
failures=0
pass() { printf 'PASS %s %s\n' "$1" "$2"; }
fail() { printf 'FAIL %s %s\n' "$1" "$2"; failures=$((failures + 1)); }
node_major_supported() { [[ "$1" =~ ^[0-9]+$ ]] && (( 10#$1 == 24 )); }

if [[ "${1:-}" == "--test-node-major" ]]; then
  [[ $# -eq 2 ]] || { printf 'Usage: %s --test-node-major MAJOR\n' "$0" >&2; exit 2; }
  if node_major_supported "$2"; then pass Node-Major-Gate "Node.js $2 accepted"; exit 0; fi
  fail Node-Major-Gate "Node.js $2 rejected; Node.js 24 LTS is required."
  exit 1
elif [[ $# -ne 0 ]]; then
  printf 'Usage: %s [--test-node-major MAJOR]\n' "$0" >&2
  exit 2
fi

if command -v docker >/dev/null 2>&1; then pass Docker "$(docker --version 2>/dev/null)"; else fail Docker 'Install Docker Engine or Docker Desktop: https://docs.docker.com/get-docker/'; fi
if command -v docker >/dev/null 2>&1 && compose_version="$(docker compose version 2>/dev/null)"; then pass Docker-Compose "$compose_version"; else fail Docker-Compose 'Install the Docker Compose plugin.'; fi
if command -v java >/dev/null 2>&1; then
  java_version="$(java -version 2>&1 | head -n 1)"
  if printf '%s' "$java_version" | grep -Eq 'version "21([."]|$)'; then pass Java "$java_version"; else fail Java 'Java 21 required; install a JDK 21 distribution.'; fi
else fail Java 'Install JDK 21 and add java to PATH.'; fi
if [[ -x "$repo_root/backend/mvnw" ]]; then pass Maven-Wrapper backend/mvnw; else fail Maven-Wrapper 'Restore the tracked executable backend Maven Wrapper.'; fi
if command -v node >/dev/null 2>&1; then
  node_version="$(node --version)"; node_major="${node_version#v}"; node_major="${node_major%%.*}"
  if node_major_supported "$node_major"; then pass Node "$node_version"; else fail Node 'Node.js 24 LTS required.'; fi
else fail Node 'Install Node.js 24 LTS.'; fi
if command -v npm >/dev/null 2>&1; then pass npm "$(npm --version)"; else fail npm 'Install npm with Node.js.'; fi
if command -v ffmpeg >/dev/null 2>&1; then pass FFmpeg "$(ffmpeg -version 2>/dev/null | head -n 1)"; else fail FFmpeg 'Install FFmpeg and add ffmpeg to PATH.'; fi

demo_env="$repo_root/.env.demo.local"
[[ -f "$demo_env" ]] || demo_env="$repo_root/.env.demo.example"
value_of() { sed -n "s/^$1=//p" "$demo_env" | head -n 1; }
check_port() {
  local name="$1" port="$2"
  [[ "$port" =~ ^[0-9]+$ && "$port" -ge 1 && "$port" -le 65535 ]] || { fail "$name-Port" 'Set a valid host port in .env.demo.local.'; return; }
  if command -v netsh.exe >/dev/null 2>&1 && netsh.exe interface ipv4 show excludedportrange protocol=tcp | awk -v p="$port" '$1 ~ /^[0-9]+$/ && p >= $1 && p <= $2 { found=1 } END { exit !found }'; then
    fail "$name-Port" "Windows reserves $port; change .env.demo.local."
  elif command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$port" | grep -q LISTEN; then
    fail "$name-Port" "$port is already listening; change .env.demo.local."
  else pass "$name-Port" "$port"; fi
}
check_port MySQL "$(value_of MYSQL_HOST_PORT)"
check_port Redis "$(value_of REDIS_HOST_PORT)"
check_port MinIO-API "$(value_of MINIO_API_HOST_PORT)"
check_port MinIO-Console "$(value_of MINIO_CONSOLE_HOST_PORT)"
check_port RocketMQ-NameServer "$(value_of ROCKETMQ_NAMESRV_HOST_PORT)"
check_port RocketMQ-Proxy "$(value_of ROCKETMQ_PROXY_HOST_PORT)"
check_port RocketMQ-Broker-Fast "$(value_of ROCKETMQ_BROKER_FAST_HOST_PORT)"
check_port RocketMQ-Broker-Main "$(value_of ROCKETMQ_BROKER_MAIN_HOST_PORT)"
check_port RocketMQ-Broker-HA "$(value_of ROCKETMQ_BROKER_HA_HOST_PORT)"
check_port Backend "$(value_of APP_PORT)"
check_port Frontend 5173

(( failures == 0 ))
