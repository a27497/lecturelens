#!/usr/bin/env bash
set -euo pipefail

task_repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$task_repo_root/backend"
bash ./mvnw -q -DskipTests compile dependency:build-classpath -Dmdep.outputFile=target/admin-classpath.txt
task_admin_classpath="target/classes:$(cat target/admin-classpath.txt)"
exec java -cp "$task_admin_classpath" com.example.courselingo.systemmodel.SystemModelAdminCli "$@"
