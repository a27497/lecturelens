"""The aggregation gate cannot turn missing or same-author reviews into PASS."""

import copy
import hashlib
import json

import pytest
from quality_gate import CANDIDATE, PACKET, POINTS, TURN_KEYS, adjudicate


def fixture():
    raw = json.dumps(
        [{"turn_key": key, "status": "completed"} for key in TURN_KEYS]
    ).encode()
    judgement = dict(
        status="PASS", reason="synthetic gate test", evidence=["synthetic span"]
    )
    review = {
        "candidate_sha256": CANDIDATE,
        "packet_sha256": PACKET,
        "outcomes_sha256": hashlib.sha256(raw).hexdigest(),
        "reviewer": {
            "name": "synthetic reviewer",
            "implementation_contributor": False,
            "independence_attested_by": "synthetic coordinator",
        },
        "turns": [
            {
                "turn_key": key,
                "points": [{"id": p, **judgement} for p in POINTS[key]],
                "claims": [copy.deepcopy(judgement)],
            }
            for key in TURN_KEYS
        ],
    }
    return raw, review


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("same_author", "UNRESOLVED"),
        ("unresolved", "UNRESOLVED"),
        ("unsupported_claim", "FAIL"),
        ("no_claim_review", "UNRESOLVED"),
        ("engineering_stop", "NOT_RUN_ENGINEERING_STOP"),
        ("complete", "PASS"),
    ],
)
def test_no_average_or_mechanical_success_hides_quality_failure(mutation, expected):
    raw, review = fixture()
    if mutation == "same_author":
        review["reviewer"]["implementation_contributor"] = True
    elif mutation == "unresolved":
        review["turns"][1]["points"][0]["status"] = "UNRESOLVED"
    elif mutation == "unsupported_claim":
        review["turns"][0]["claims"][0]["status"] = "FAIL"
    elif mutation == "no_claim_review":
        review["turns"][0]["claims"] = []
    elif mutation == "engineering_stop":
        rows = json.loads(raw)
        rows[0]["status"] = "failed"
        raw = json.dumps(rows).encode()
        review["outcomes_sha256"] = hashlib.sha256(raw).hexdigest()
    assert adjudicate(review, raw)["quality"] == expected


@pytest.mark.parametrize(
    "mutation", ["missing_point", "missing_position", "wrong_binding", "no_evidence"]
)
def test_incomplete_review_is_invalid(mutation):
    raw, review = fixture()
    if mutation == "missing_point":
        review["turns"][0]["points"].pop()
    elif mutation == "missing_position":
        review["turns"].pop()
    elif mutation == "wrong_binding":
        review["outcomes_sha256"] = "0" * 64
    else:
        review["turns"][0]["points"][0]["evidence"] = []
    with pytest.raises(ValueError):
        adjudicate(review, raw)


def test_trusted_reference_trace_not_a_generated_answer():
    names, length, trace, inner = ["Ada", "Grace"], 2, [2], []
    for _ in names:
        length += 1
        trace.append(length)
        inner.append(length)
    assert trace == [2, 3, 4] and length == 4 and inner == [3, 4]
    assert names[0] == "Ada" and names[1] == "Grace"
