"""Quote binding and schema checks for diagnostics, not semantic accuracy."""

import pytest
from relation_probe import validate_response

SOURCE = "A valid ticket contains a code."
CLAIM = "Each valid ticket contains a code."


def response(**changes):
    return {
        "calls": [
            {
                "name": "assess_source_relation",
                "arguments": {
                    "source_relation": "definition",
                    "source_quote": SOURCE,
                    "claim_quote": CLAIM,
                    "gap": "none",
                    "supported": True,
                    **changes,
                },
            }
        ]
    }


def test_quote_must_come_from_the_supplied_source():
    with pytest.raises(ValueError, match="Source quote"):
        validate_response(response(), "An unrelated ticket has a name.", CLAIM)


def test_gap_quote_cannot_invent_a_claim_or_revision():
    with pytest.raises(ValueError, match="Claim quote"):
        validate_response(response(claim_quote="The code is signed."), SOURCE, CLAIM)


def test_valid_literal_quote_does_not_override_a_rejection():
    verdict = validate_response(
        response(supported=False, gap="changed_scope"), SOURCE, CLAIM
    )
    assert not verdict.supported


@pytest.mark.parametrize("count", [0, 2])
def test_missing_or_duplicate_judgments_are_not_a_pass(count):
    result = response()
    result["calls"] *= count
    with pytest.raises(ValueError, match="Exactly one"):
        validate_response(result, SOURCE, CLAIM)


def test_unknown_gap_is_a_protocol_failure_not_semantic_rejection():
    with pytest.raises(ValueError):
        validate_response(response(supported=False, gap="probably"), SOURCE, CLAIM)


@pytest.mark.parametrize(
    "changes", [{"supported": False}, {"gap": "untaught_property"}]
)
def test_support_cannot_disagree_with_gap(changes):
    with pytest.raises(ValueError, match="Support and gap"):
        validate_response(response(**changes), SOURCE, CLAIM)


def test_freeform_observation_cannot_add_an_unsourced_correction():
    with pytest.raises(ValueError):
        validate_response(response(observation="The source means X."), SOURCE, CLAIM)
