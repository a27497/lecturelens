"""Explicit user billing-risk consent for one fixed run; never issues or renews grants."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

AUTHORITY = (
    Path(__file__).resolve().parents[1]
    / "phase1b-smoke-2227-20261108/USER_AUTHORIZATION.json"
)
AUTHORITY_SHA256 = "d08d552ebd0aace059f908d05490635d12ebb29f01262cc54f69b5be827000bf"
KIND = "EXPLICIT_USER_FIXED_RUN_BILLING_RISK"
RUN_ID = "v19-smoke-20261108-2227-once"
WALL_SECONDS = 180
MIN_REMAINING_SECONDS = 185
SCOPE_KEYS = (
    "run_id",
    "execution_root",
    "git_head",
    "candidate_sha256",
    "packet_sha256",
    "scope",
    "model",
    "endpoint",
    "ordinary_decisions_per_turn",
    "shared_finish_corrections_per_turn",
    "max_requests",
    "max_output_tokens",
    "max_nano_usd",
    "concurrency",
    "transport_retries",
    "reviewer_calls",
    "embedding_calls",
)


def utcnow():
    return datetime.now(timezone.utc)


def authority():
    raw = AUTHORITY.read_bytes()
    if hashlib.sha256(raw).hexdigest() != AUTHORITY_SHA256:
        raise ValueError("EXPLICIT_USER_AUTHORIZATION_RECORD_CHANGED")
    return json.loads(raw)


def record_paths(root):
    root = Path(root)
    return (
        root / ".data/tutor-v19-authorizations" / (RUN_ID + ".used"),
        root / ".data/tutor-v19-outer-once" / (RUN_ID + ".started"),
        root / ".data" / RUN_ID,
    )


def available(root):
    # lexists semantics also reject dangling symlinks; they are not unused slots.
    if any(p.exists() or p.is_symlink() for p in record_paths(root)):
        raise ValueError("FIXED_RUN_ALREADY_CLAIMED_STARTED_OR_OBSERVED")


def status(root):
    data = authority()
    expires = datetime.fromisoformat(data["outer_expires_utc"])
    current = utcnow()
    available(root)
    return {
        "run_id": RUN_ID,
        "authority_sha256": AUTHORITY_SHA256,
        "outer_expires_utc": data["outer_expires_utc"],
        "valid_now": current < expires,
        "remaining_seconds": max(0, int((expires - current).total_seconds())),
        "risk_accepted_for_fixed_run_only": current < expires,
    }


def validate(data, grant, current_head, now=None):
    expected = authority()
    now = now or utcnow()
    try:
        valid = (
            data["kind"] == KIND
            and data["accepted"] is True
            and data["authority_sha256"] == AUTHORITY_SHA256
            and data["statement"] == expected["statement"]
            and data["outer_expires_utc"] == expected["outer_expires_utc"]
            and data["supplier_may_exceed_local_cap"] is True
            and data["supplier_absolute_cap_verified"] is False
            and data["preparation_git_head"]
            == grant["preparation_git_head"]
            == current_head
            and data["issued_utc"] == grant["issued_utc"]
            and data["expires_utc"] == grant["expires_utc"]
        )
        for key in SCOPE_KEYS:
            valid = valid and all(
                type(obj[key]) is type(expected[key]) and obj[key] == expected[key]
                for obj in (data, grant)
            )
        issued, expires = (
            datetime.fromisoformat(data[k]) for k in ("issued_utc", "expires_utc")
        )
        outer = datetime.fromisoformat(expected["outer_expires_utc"])
        valid = (
            valid
            and issued.tzinfo is not None
            and expires.tzinfo is not None
            and issued <= now < expires <= outer
            and 0 < (expires - issued).total_seconds() <= 900
            and (expires - now).total_seconds() >= MIN_REMAINING_SECONDS
        )
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError("FIXED_RUN_EXPLICIT_RISK_BINDING_OR_DEADLINE_INVALID")
    available(expected["execution_root"])
    return data


def begin_handoff(root, grant, authorization, pricing, assurance):
    """Persist a single-use start before exec; crashes/exec failure are never retried."""
    available(root)
    expires = datetime.fromisoformat(grant["expires_utc"])
    outer = datetime.fromisoformat(authority()["outer_expires_utc"])
    if (min(expires, outer) - utcnow()).total_seconds() < MIN_REMAINING_SECONDS:
        raise ValueError("FIXED_RUN_TOO_CLOSE_TO_EXPIRY_NO_EXTENSION")
    from lecturelens_real_eval.tutor.diagnostic_capture import private_file

    path = record_paths(root)[1]
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    record = {
        "run_id": RUN_ID,
        "preparation_git_head": grant["preparation_git_head"],
        "expires_utc": grant["expires_utc"],
        "started_utc": utcnow().isoformat(),
        "state": "HANDOFF_STARTED_NO_AUTOMATIC_RETRY",
        "files": {
            str(p): hashlib.sha256(Path(p).read_bytes()).hexdigest()
            for p in (authorization, pricing, assurance)
        },
    }
    private_file(path, json.dumps(record, sort_keys=True).encode())
