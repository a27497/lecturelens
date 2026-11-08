"""Fixed-run handoff from the user's already credentialed terminal, never a key bridge."""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "phase1b-tutor-diagnostic-20261108"))
import admission
import risk_once

ROOT = HERE.parents[1]
PRICE = HERE / "TERMINAL_PRICE_RECEIPT.json"
DATABASE = HERE / "TERMINAL_DATABASE.json"
RECEIPTS = ROOT / ".data/smoke-2227/terminal-once-receipts"


def database_identity():
    expected = admission.load(DATABASE)
    # This child needs no provider environment. Never inspect Docker's Env field.
    fmt = (
        '{"id":{{json .Id}},"image":{{json .Image}},'
        '"running":{{json .State.Running}},'
        '"run_id":{{json (index .Config.Labels "lecturelens.run_id")}},'
        '"ports":{{json .NetworkSettings.Ports}},"mounts":{{json .Mounts}},'
        '"restart":{{json .HostConfig.RestartPolicy.Name}}}'
    )
    actual = json.loads(
        subprocess.check_output(
            ["/usr/bin/docker", "inspect", "--format", fmt, expected["id"]],
            env={"PATH": "/usr/bin:/bin"},
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    )
    valid = (
        actual["id"] == expected["id"]
        and actual["image"] == expected["image"]
        and actual["running"] is True
        and actual["run_id"] == risk_once.RUN_ID
        and actual["restart"] == "no"
        and actual["ports"]["5432/tcp"]
        == [{"HostIp": "127.0.0.1", "HostPort": "25841"}]
        and any(
            m.get("Type") == "volume"
            and m.get("Name") == expected["volume"]
            and m.get("Destination") == "/var/lib/postgresql/data"
            and m.get("RW") is True
            for m in actual["mounts"]
        )
    )
    if not valid:
        raise ValueError("FIXED_NEW_DATABASE_IDENTITY_CHANGED")
    admission.database_ready()


def issue_and_handoff(expected_head):
    # Only membership is inspected here. The unchanged provider reads the value
    # after admission; exec inherits it directly from the user's own terminal.
    if "AGENT_LLM_API_KEY" not in os.environ:
        raise ValueError("RUNTIME_KEY_NOT_INJECTED")
    head = admission.preparation_head()
    if head != expected_head:
        raise ValueError("FINAL_PREPARATION_HEAD_CHANGED")
    authority = risk_once.authority()
    root = Path(authority["execution_root"])
    state = admission.inspect(root)
    risk_once.available(root)
    plan_hash = admission.review_plan(admission.POLICY)
    price = admission.load(PRICE)
    if not admission.fresh(price["reviewed_utc"], 86400):
        raise ValueError("PRICE_REVIEW_EXPIRED_NO_AUTOMATIC_REFRESH")
    database_identity()
    now = datetime.now(timezone.utc)
    outer = datetime.fromisoformat(authority["outer_expires_utc"])
    expires = min(now + timedelta(minutes=15), outer)
    common = {key: authority[key] for key in risk_once.SCOPE_KEYS}
    common.update(
        preparation_git_head=head,
        issued_utc=now.isoformat(),
        expires_utc=expires.isoformat(),
    )
    risk = dict(
        common,
        kind=risk_once.KIND,
        accepted=True,
        authority_sha256=risk_once.AUTHORITY_SHA256,
        statement=authority["statement"],
        outer_expires_utc=authority["outer_expires_utc"],
        supplier_may_exceed_local_cap=True,
        supplier_absolute_cap_verified=False,
    )
    grant = dict(common, authorized=True, review_plan_sha256=plan_hash)
    risk_once.validate(risk, grant, head, now=now)
    # Directory creation is the issuance lock. Partial issuance is deliberately
    # retained and cannot be renewed by invoking this entry again.
    RECEIPTS.mkdir(mode=0o700)
    from lecturelens_real_eval.tutor.diagnostic_capture import private_file

    def save(name, value):
        path = RECEIPTS / name
        private_file(path, json.dumps(value, sort_keys=True).encode())
        return path

    assurance = save("risk.json", risk)
    grant["cost_assurance_sha256"] = admission.digest(assurance)
    authorization = save("grant.json", grant)
    pricing = save("pricing.json", price)
    os.environ["LECTURELENS_REAL_EVAL"] = "1"
    from lecturelens_real_eval.tutor.selection_smoke import live_admission

    live_admission(state["frozen"], authorization, pricing)
    admission.handoff(
        root,
        root / ".data" / risk_once.RUN_ID,
        authorization,
        pricing,
        assurance,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args()
    try:
        issue_and_handoff(args.expected_head)
    except Exception:  # noqa: BLE001 -- do not copy provider/connection exception text
        print("FIXED_RUN_HANDOFF_BLOCKED_NO_AUTOMATIC_RETRY")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
