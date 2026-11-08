#!/usr/bin/env bash
# Run only from the terminal where the user exported the provider variable.
set +x
set +e
umask 077
if [[ $# != 1 || ${AGENT_LLM_API_KEY+present} != present ]]; then
    printf '%s\n' 'BLOCKED: expected HEAD and inherited AGENT_LLM_API_KEY required; value not read.'
    exit 2
fi
task_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P) || exit 2
audit_root="$task_root/.data/smoke-2227/terminal-handoff"
set -o noclobber
# The log is exclusive even if interruption happens before native claiming.
/home/dev/.codex/worktrees/phase1a-v19-runner-20261108/agent-service/.venv/bin/python \
    "$task_root/eval/phase1b-smoke-2227-20261108/terminal_once.py" \
    --expected-head "$1" > "$audit_root/live-terminal.log" 2>&1
smoke_exit=$?
printf '%s\n' "$smoke_exit" > "$audit_root/live-terminal.exit"
printf 'SMOKE_EXIT=%s\nEvidence: %s\n' "$smoke_exit" "$audit_root"
exit "$smoke_exit"
