#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
contract='^[a-z0-9-]{1,32}$'
exactly_32="$(printf 'a%.0s' {1..32})"
exactly_33="$(printf 'a%.0s' {1..33})"

assert_case() {
  local name="$1" value="$2" expected="$3" actual=false
  [[ "$value" =~ $contract ]] && actual=true
  [[ "$actual" == "$expected" ]] || { printf 'FAIL instance-name-%s expected=%s actual=%s\n' "$name" "$expected" "$actual" >&2; exit 1; }
  printf 'PASS instance-name-%s accepted=%s\n' "$name" "$actual"
}

assert_case one-character a true
assert_case over-twelve-characters bash-zero-audit true
assert_case exactly-thirty-two-characters "$exactly_32" true
assert_case thirty-three-characters "$exactly_33" false
assert_case uppercase Demo false
assert_case underscore demo_instance false
assert_case empty '' false

for name in start-infrastructure.sh stop-infrastructure.sh; do
  grep -Fq '^[a-z0-9-]{1,32}$' "$script_dir/$name"
  grep -Fq 'LECTURELENS_DEMO_INSTANCE must match [a-z0-9-]{1,32}.' "$script_dir/$name"
  printf 'PASS instance-name-contract script=%s\n' "$name"
done
