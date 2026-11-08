"""Read-only readiness inspection. There is deliberately no live execution option."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

V19_HEAD = "2ecf4d52af1084bad405e98a6e78027bf4c5ab5d"
PHASE0_HEAD = "17d78636cf97fcf55fe642b1ecc30c5e2ea48865"
CANDIDATE = "16a094317ba06b3c1932280c7dbb15a07d47200dc74ed8e08e25465e10549ae9"
PACKET = "ade24dceaf2bf50421b88373b68ebb65ba776c0d83754cab350fc06f558ba60e"


def inspect(root):
    root = Path(root).resolve()

    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args])

    if git("rev-parse", "HEAD").decode().strip() != V19_HEAD:
        raise ValueError("EXACT_V19_EXECUTION_HEAD_REQUIRED")
    if git("status", "--porcelain"):
        raise ValueError("CLEAN_V19_CHECKOUT_REQUIRED")
    sys.path.insert(0, str(root / "agent-service/src"))
    from lecturelens_real_eval.tutor.selection_smoke import verify_inputs

    state = verify_inputs()
    if state["candidate_sha256"] != CANDIDATE or state["packet_sha256"] != PACKET:
        raise ValueError("FROZEN_IDENTITY_MISMATCH")
    source = "backend/src/main/java/com/example/courselingo/study/StudyEvidenceAuthority.java"
    phase0 = git("show", PHASE0_HEAD + ":" + source)
    selected = (root / source).read_bytes()
    return {
        "phase0_head": PHASE0_HEAD,
        "execution_head": V19_HEAD,
        "execution_root": str(root),
        "frozen": state,
        "credential_presence_only": {
            "AGENT_LLM_API_KEY": "AGENT_LLM_API_KEY" in os.environ,
            "value_read": False,
            "nonempty_or_valid": "NOT_CHECKED",
        },
        "compatibility": {
            "phase0_authority_sha256": hashlib.sha256(phase0).hexdigest(),
            "v19_authority_sha256": hashlib.sha256(selected).hexdigest(),
            "phase0_complete_v1": b'"complete-v1"' in phase0,
            "v19_complete_v1": b'"complete-v1"' in selected,
            "integrated_acceptance": "NOT_RUN_NOT_COMPATIBLE_WITH_UNCHANGED_PHASE0_GATEWAY",
        },
        "local_reservation_worst_nano_usd": 12 * (65536 * 300 + 4096 * 1200),
        "supplier_hard_cap": "UNVERIFIED_NOT_ENFORCED_BY_LOCAL_LEDGER",
        "authorized": False,
        "admission_ready": False,
        "real_requests": 0,
        "quality": "NOT_RUN",
        "phase0_remote_ci": "PENDING",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.candidate_root)
    with open(args.output, "x", opener=lambda p, f: os.open(p, f, 0o600)) as target:
        json.dump(result, target, indent=2)
        target.write("\n")
    print(
        json.dumps({"frozen_inputs": "PASS", "authorized": False, "real_requests": 0})
    )


if __name__ == "__main__":
    main()
