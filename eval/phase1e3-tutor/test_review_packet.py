import json
import unittest
from copy import deepcopy

from review_packet import make_packet, reviewed_pass


class ReviewPacketTest(unittest.TestCase):
    def test_binds_two_complete_independent_reviews_and_preserves_uncertainty(self):
        case = {
            "id": "sql-1",
            "question": "Explain the denominator",
            "socratic": False,
            "expected_outcome": "answered",
            "required_checks": ["Correct count"],
        }
        turn = {
            "answer": "Fixture [e1]",
            "outcome": "answered",
            "checkpoint": {
                "messages": [
                    {
                        "content": json.dumps(
                            {
                                "dialogue": [],
                                "current_evidence": [
                                    {"evidence_id": "e1", "text": "Fixture evidence"}
                                ],
                            }
                        )
                    }
                ]
            },
        }
        packet = make_packet(case, turn, {"sqlite": [2]})
        point = {"verdict": "PASS", "basis": "fixture span"}
        review = {
            "packet_sha256": packet["packet_sha256"],
            "confidence": "HIGH",
            "severe_error": False,
            "checks": {"1": point},
            "claim_checks": [{**point, "claim": "Fixture", "evidence_id": "e1"}],
            "citation_and_teaching_check": point,
        }
        reviews = [
            {**review, "model": "fake-a", "independent_context": "a"},
            {**review, "model": "fake-b", "independent_context": "b"},
        ]
        assert reviewed_pass(packet, reviews)
        assert not reviewed_pass(packet, reviews[:1])
        for change in (
            {"packet_sha256": "bad"},
            {"model": "fake-a"},
            {"independent_context": "a"},
            {"confidence": "LOW"},
            {"checks": {}},
            {"claim_checks": [{**point, "evidence_id": "not-delivered"}]},
            {"severe_error": True},
        ):
            changed = deepcopy(reviews)
            changed[1].update(change)
            assert not reviewed_pass(packet, changed)
