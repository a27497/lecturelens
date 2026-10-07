"""Exact span/authority/revision mechanics; fixtures do not prove model quality."""

import copy
import json

import httpx
import pytest
from pydantic import ValidationError
from test_study import read, setup  # noqa: F401

from lecturelens_agent.study.atomic import atomic_claims, validate_claims
from lecturelens_agent.study.atomic_review import AtomicAnswerVerdict
from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.provider import ChatProvider, ModelResponseError
from lecturelens_agent.study.quality import review_messages, review_schema
from lecturelens_agent.study.review_diagnostics import atomic_review_detail
from lecturelens_agent.study.strengthening import strengthening_guards

CLIENT = httpx.Client


def test_measured_input_approximation_is_not_promoted_to_exact_sample_size():
    exact = atomic_claims("When n is 3 million, the run takes 4 seconds.")[0]
    approximate = atomic_claims("When n is about 3 million, the run takes 4 seconds.")[0]
    source = "When n is around 3 million or so, the run takes 4 seconds."
    assert "input_precision" in strengthening_guards(exact, [source])
    assert "input_precision" not in strengthening_guards(approximate, [source])
    hypothetical = atomic_claims("For n=8, the logarithmic scale is 3.")[0]
    assert "input_precision" not in strengthening_guards(hypothetical, [source])


def test_unsourced_composite_branch_cannot_hide_across_atomic_boundaries():
    source = "The method compares a candidate with its neighbours and recurses on a half-sized input."
    answer = (
        "先比较某个元素与相邻元素。"
        "根据比较结果，选择一个邻居（更大的一侧）对应的子数组进行递归处理。"
        "每轮输入规模减半。"
    )
    claims = atomic_claims(answer)
    rejected = [
        c["source_text"].strip()
        for c in claims
        if "branch_specialization" in strengthening_guards(c, [source])
    ]
    assert rejected == ["选择一个邻居", "（更大的一侧）", "对应的子数组进行递归处理。"]
    assert "branch_specialization" not in strengthening_guards(claims[-1], [source])
    taught = source + " It chooses the larger neighbouring side and recurses there."
    assert all("branch_specialization" not in strengthening_guards(c, [taught]) for c in claims)


def test_possible_count_and_unsourced_post_stop_mutation_are_not_strengthened():
    source = "Each iteration potentially makes two comparisons, then the input halves until the one-item base case returns."
    fixed = atomic_claims("Each iteration makes two comparisons.")[0]
    bounded = atomic_claims("Each iteration makes at most two comparisons.")[0]
    assert "count_modality" in strengthening_guards(fixed, [source])
    assert "count_modality" not in strengthening_guards(bounded, [source])
    stopped = atomic_claims("The algorithm returns at the base case and makes no further modification.")[-1]
    assert "input_mutation_policy" in strengthening_guards(stopped, [source])


def test_chinese_contrast_connectives_remain_whole_with_lossless_coverage():
    answer = "旧对象仍然存在。然而，变量 v 不再引用旧对象，而是指向新对象。"
    claims = atomic_claims(answer)
    assert "".join(c["source_text"] for c in claims) == answer
    assert [c["source_text"] for c in claims] == [
        "旧对象仍然存在。",
        "然而，变量 v 不再引用旧对象，",
        "而是指向新对象。",
    ]
    validate_claims(answer, claims)


@pytest.mark.parametrize("prefix", ["课程中指出，", "根据课程内容，", "According to the course, "])
def test_bare_source_attribution_is_bound_to_the_following_assertion(prefix):
    answer = prefix + "The gate is open."
    claims = atomic_claims(answer)
    assert len(claims) == 1 and claims[0]["source_text"] == answer
    validate_claims(answer, claims)


CASES = [
    ("and", "The gate is open and a warning bell rings.", "The gate is open.", "and a warning bell rings."),
    ("time", "The gate is open until the timer expires.", "The gate is open.", "until the timer expires."),
    (
        "cause",
        "The gate is open because the sensor detects a car.",
        "The gate is open.",
        "because the sensor detects a car.",
    ),
    (
        "effect",
        "The gate is open, therefore every car can leave.",
        "The gate is open.",
        "therefore every car can leave.",
    ),
    (
        "conditional",
        "The gate is open if a ticket is scanned.",
        "The gate is open.",
        "if a ticket is scanned.",
    ),
    (
        "quantity",
        "The gate opens for exactly three minutes.",
        "The gate opens.",
        "The gate opens for exactly three minutes.",
    ),
    ("negative", "The gate never closes.", "The gate opens.", "The gate never closes."),
    (
        "parenthesis",
        "旧 hello 对象仍在内存中（直到被垃圾回收），但 s 不再引用它。",
        "旧 hello 对象当时仍在内存中，s 不再引用它。",
        "（直到被垃圾回收），",
    ),
]


def body(answer, evidence="The gate is open."):
    return json.loads(
        review_messages(
            "Explain the state.",
            {"kind": "explanation", "title": "State", "explanation": answer, "evidence_ids": ["canonical"]},
            [
                {"evidence_id": "canonical", "text": evidence},
                {"evidence_id": "uncited", "text": "EXTERNAL OMITTED"},
            ],
            answer_review_mode="atomic_answer_support_v1",
        )[-1]["content"]
    )


def _judgment(b, rejected=()):
    if b.get("goal_scope_binding"):
        from lecturelens_agent.study.goal_obligations import carries_obligation

        # Scoped wire targets use offsets into the full current answer.
        b = {
            **b,
            "atomic_claims": [
                {
                    **c,
                    "source_text": c.get(
                        "source_text", b["candidate"]["explanation"][c.get("start", 0) : c.get("end", 0)]
                    ),
                }
                for c in b["atomic_claims"]
            ],
        }
        return {
            "goal_checks": [
                {
                    "id": o["id"],
                    "status": "satisfied",
                    "answer_quote": next(
                        (
                            c["source_text"].strip()[:400]
                            for c in b["atomic_claims"]
                            if o["kind"] == "whole_goal" or carries_obligation(o, c["source_text"])
                        ),
                        b["candidate"]["explanation"][:400],
                    ),
                }
                for o in b["goal_scope_binding"]["obligations"]
            ],
            "claim_checks": [
                {"id": c["id"], "supported": c["source_text"].strip() not in rejected, "evidence_ids": ["e1"]}
                for c in b["atomic_claims"]
            ],
        }
    return {
        "goal_checks": [
            {
                "id": g["id"],
                "matches": True,
                "observation": "The answer states the outcome.",
                **(
                    {
                        "answer_claim_ids": [
                            b["goal_answer_claims"][0][0]
                            if "goal_answer_claims" in b
                            else b["atomic_claims"][0]["id"]
                        ]
                    }
                    if b["review_mode"] in {"atomic_answer_spans_v2", "atomic_delta_spans_v2"}
                    else {"answer_quotes": [b["candidate"]["explanation"][:150]]}
                ),
            }
            for g in b["goal_constraints"]
        ],
        "claim_checks": [
            {"id": c["id"], "supported": c["source_text"].strip() not in rejected, "evidence_ids": ["e1"]}
            for c in b["atomic_claims"]
        ],
    }


def response(verdict):
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "type": "function",
                                "function": {
                                    "name": "assess_study_candidate",
                                    "arguments": json.dumps(verdict),
                                },
                            }
                        ]
                    }
                }
            ]
        },
    )


@pytest.mark.parametrize("name,answer,narrowed,extra", CASES, ids=[c[0] for c in CASES])
def test_exact_coverage_exposes_all_qualifiers_and_never_rewrites(name, answer, narrowed, extra):
    claims = atomic_claims(answer)
    assert any(c["source_text"].strip() == extra for c in claims)
    assert "".join(c["source_text"] for c in claims) == answer
    for c in claims:
        assert answer[c["start"] : c["end"]] == c["source_text"]
        assert c["normalized_claim"] == " ".join(c["source_text"].split())
    assert "垃圾回收" not in __import__("inspect").getsource(atomic_claims)


def test_unicode_offsets_quotes_decimals_nested_parentheses_and_tail():
    text = '😀 s = "a,b"，值是 3.14（只在条件满足时（不超过 2 次））！尾部否定：不是无限次'
    claims = atomic_claims(text)
    assert "".join(c["source_text"] for c in claims) == text
    assert any('"a,b"' in c["source_text"] for c in claims)
    assert any("3.14" in c["source_text"] for c in claims)
    assert any("不超过 2 次" in c["source_text"] for c in claims)
    assert claims[-1]["source_text"].endswith("不是无限次")


def test_math_arguments_remain_inside_assertions_and_prose_qualifiers_stay_separate():
    text = "F(m) = F(m/3) + Ω(1)，每次进行 Ω(1) 工作（直到被删除）。"
    claims = atomic_claims(text)
    assert "".join(c["source_text"] for c in claims) == text
    assert len(claims) == 3
    assert claims[0]["source_text"] == "F(m) = F(m/3) + Ω(1)，"
    assert claims[-1]["source_text"] == "（直到被删除）。"


def test_subscripted_function_arguments_are_not_detached_as_prose():
    text = "j = log₃(m)，每层工作为 Ω(1)（若条件成立）。"
    claims = atomic_claims(text)
    assert "".join(c["source_text"] for c in claims) == text
    assert claims[0]["source_text"] == "j = log₃(m)，"
    assert claims[-1]["source_text"] == "（若条件成立）。"
    mathematical = "Ω(log₃m) 是增长形式，log₃(m) 是层数。"
    assert all("(log₃m)" != c["source_text"].strip() for c in atomic_claims(mathematical))
    assert atomic_claims(mathematical)[0]["source_text"] == "Ω(log₃m) 是增长形式，"


def test_structural_prefixes_bind_to_the_following_assertion_without_losing_scope():
    text = "1. **First method**:\nA is ready.\n2. **Second method**:\nB runs. 因此，所有对象都消失。"
    claims = atomic_claims(text)
    assert "".join(c["source_text"] for c in claims) == text
    assert claims[0]["source_text"].startswith("1. **First method**:")
    assert "A is ready." in claims[0]["source_text"]
    assert claims[-1]["source_text"] == "因此，所有对象都消失。"


@pytest.mark.parametrize("prefix", ["具体来说，", "具体而言，", "换句话说，", "For example, "])
def test_discourse_marker_is_verified_with_its_assertion_including_unsupported_position(prefix):
    answer = prefix + "Inspect the middle element."
    b = body(answer, "Inspect an element and its neighbours.")
    assert len(b["atomic_claims"]) == 1 and b["atomic_claims"][0]["source_text"] == answer
    verdict = AtomicAnswerVerdict.model_validate(judgment(b), context=b).review()
    assert verdict.issues == ["unsupported_explanation"]
    assert verdict.atomic_assessments[0].strengthening_guards == ["position_specialization"]


def test_bounded_claims_never_silently_drop_a_tail():
    with pytest.raises(ValueError, match="1 and 24"):
        atomic_claims("A. " * 25)


def test_context_cannot_be_replaced_by_supporting_evidence():
    b = body("The gate is open until the timer expires.")
    b["atomic_claims"][1]["context_text"] = "The gate is open."
    with pytest.raises(ValueError, match="same answer"):
        validate_claims(b["candidate"]["explanation"], b["atomic_claims"])


def test_goal_still_requires_the_current_answer_not_only_evidence():
    b = body("The gate is open.")
    v = judgment(b)
    v["goal_checks"][0]["answer_quotes"] = ["The timer expires."]
    with pytest.raises(ValidationError, match="actual answer"):
        AtomicAnswerVerdict.model_validate(v, context=b)


def test_goal_quote_schema_offers_contiguous_answer_anchors_without_relaxing_binding():
    b = body("The gate is open. The bell rings.")
    schema = review_schema("explanation", review_mode="atomic_answer_support_v1", context=b)
    options = schema["function"]["parameters"]["$defs"]["AnswerGoalCheck"]["properties"]["answer_quotes"][
        "items"
    ]["enum"]
    assert options == ["The gate is open.", "The bell rings."]
    v = judgment(b)
    v["goal_checks"][0]["answer_quotes"] = ["The gate...The bell rings."]
    with pytest.raises(ValidationError, match="actual answer"):
        AtomicAnswerVerdict.model_validate(v, context=b)
    v["goal_checks"][0]["answer_quotes"] = options
    assert AtomicAnswerVerdict.model_validate(v, context=b).review().issues == []


def test_rejected_qualifier_allows_empty_evidence_without_contract_correction():
    b = body("The gate is open until the timer expires.")
    v = judgment(b)
    v["claim_checks"][-1].update(supported=False, evidence_ids=[])
    if v["claim_checks"][-1].get("relation"):
        v["claim_checks"][-1]["relation"]["grounds"] = []
    review = AtomicAnswerVerdict.model_validate(v, context=b).review()
    assert review.issues == ["unsupported_explanation"]
    assert review.atomic_assessments[-1].evidence_ids == []
    assert not review.atomic_assessments[-1].supported
    from lecturelens_agent.study.atomic import AtomicAssessment

    assert AtomicAssessment.model_validate(review.atomic_assessments[-1].model_dump()).supported is False
    v["claim_checks"][-1]["supported"] = True
    with pytest.raises(ValidationError, match="require Evidence"):
        AtomicAnswerVerdict.model_validate(v, context=b)


@pytest.mark.parametrize(
    "fault", ["offset", "source", "normalization", "omission", "duplicate", "tail", "context"]
)
def test_forged_or_incomplete_binding_is_rejected(fault):
    b = body("The gate is open until the timer expires.")
    claims = b["atomic_claims"]
    if fault == "offset":
        claims[0]["end"] -= 1
    elif fault == "source":
        claims[0]["source_text"] = "Another fact."
    elif fault == "normalization":
        claims[1]["normalized_claim"] = "The gate is open."
    elif fault == "omission":
        claims.pop(0)
    elif fault == "duplicate":
        claims.append(copy.deepcopy(claims[0]))
    elif fault == "tail":
        claims.pop()
    else:
        claims[1]["context_end"] = 1
    with pytest.raises(ValueError):
        validate_claims(b["candidate"]["explanation"], claims)


@pytest.mark.parametrize("supported", [False, True])
@pytest.mark.parametrize("refs", [["e2"], ["e1", "e1"], ["invented"]])
def test_citation_authority_remains_strict_for_every_verdict(supported, refs):
    b = body("The gate is open.")
    v = judgment(b)
    v["claim_checks"][0].update(supported=supported, evidence_ids=refs)
    b["allowed_evidence_ids_for_answer_support"].append("e2")
    with pytest.raises(ValidationError, match="own observed citations"):
        AtomicAnswerVerdict.model_validate(v, context=b)


@pytest.mark.parametrize("fault", ["missing", "duplicate", "wrong", "course_fact"])
def test_every_claim_once_and_no_course_fact_adapter(fault):
    b = body("The gate is open until the timer expires.")
    v = judgment(b)
    if fault == "missing":
        v["claim_checks"].pop()
    elif fault == "duplicate":
        v["claim_checks"][1]["id"] = "a1"
    elif fault == "wrong":
        v["claim_checks"][1]["id"] = "a9"
    else:
        v["claim_checks"][0]["course_fact"] = "The gate is open."
    with pytest.raises(ValidationError):
        AtomicAnswerVerdict.model_validate(v, context=b)


def test_provider_only_sees_candidate_owned_evidence_and_exact_claims(monkeypatch):
    captured = []

    def handle(request):
        wire = json.loads(request.content)
        captured.append(wire)
        b = json.loads(wire["messages"][-1]["content"])
        assert len(b["evidence"]) == 1 and b["evidence"][0]["evidence_id"] == "e1"
        assert b["review_mode"] == "atomic_answer_spans_v2"
        assert (
            "course_fact"
            not in wire["tools"][0]["function"]["parameters"]["$defs"]["AtomicCheck"]["properties"]
        )
        return response(judgment(b, ["until the timer expires."]))

    monkeypatch.setattr(httpx, "Client", lambda **kw: CLIENT(transport=httpx.MockTransport(handle), **kw))
    messages = review_messages(
        "Explain the state.",
        {
            "kind": "explanation",
            "title": "State",
            "explanation": "The gate is open until the timer expires.",
            "evidence_ids": ["canonical"],
        },
        [
            {"evidence_id": "canonical", "text": "The gate is open."},
            {"evidence_id": "extra", "text": "until the timer expires"},
        ],
    )
    result = ChatProvider("https://fixture.invalid/v1", "qwen3-max", "fixture-key").review(messages, 10)
    assert result["review"]["issues"] == ["unsupported_explanation"]
    assert "until the timer expires" in result["review"]["feedback"]
    assert captured[0]["max_tokens"] == 1600
    assert captured[0]["model"] == "qwen3-max"


@pytest.mark.parametrize(
    "name,answer,narrowed,extra", CASES[:5] + [CASES[-1]], ids=[c[0] for c in CASES[:5] + [CASES[-1]]]
)
def test_atomic_rejection_drives_minimal_revision_without_extra_search(
    setup,  # noqa: F811
    monkeypatch,
    name,
    answer,
    narrowed,
    extra,  # noqa: F811
):
    store, authority, runtime, scope = setup
    original_read, original_decide = authority.read, runtime.provider.decide
    decisions, requests = [], []

    def course_read(current_scope, action="CHECK", **arguments):
        result = original_read(current_scope, action, **arguments)
        for e in result.get("evidence", []):
            e["text"] = narrowed
        return result

    def decide(messages, timeout):
        b = json.loads(messages[-1]["content"])
        if not b["evidence"]:
            return original_decide(messages, timeout)
        decisions.append(b)
        if len(decisions) == 2:
            assert "unsupported_explanation" in b["quality"]["issues"]
            assert extra in b["quality"]["feedback"]
            assert "atomic_assessments" not in b["quality"]
            assert any(extra in c["text"] for c in b["revision_transaction"]["rejected"])
        if len(decisions) == 2:
            return {
                "name": "create_explanation",
                "arguments": {
                    "revision_edits": [
                        {
                            "id": b["revision_transaction"]["rejected"][0]["id"],
                            "replacement": "，" if name == "parenthesis" else ".",
                        }
                    ]
                },
            }
        return {
            "name": "create_explanation",
            "arguments": {"title": "State", "explanation": answer, "evidence_ids": ["e1"]},
        }

    def handle(request):
        b = json.loads(json.loads(request.content)["messages"][-1]["content"])
        requests.append(b)
        return response(judgment(b, [extra] if len(requests) == 1 else []))

    authority.read = course_read
    runtime.provider.decide = decide
    monkeypatch.setattr(httpx, "Client", lambda **kw: CLIENT(transport=httpx.MockTransport(handle), **kw))
    runtime.provider.review = ChatProvider("https://fixture.invalid/v1", "qwen3-max", "fixture-key").review
    monkeypatch.setenv("AGENT_PRIVATE_REVIEW_TELEMETRY_SESSION", scope["session_id"])
    started = store.command(
        StudyCommand(**scope, operation="START", request_key="atomic", goal="Explain the state."), "mock"
    )
    run = next(r for r in store.candidates() if r["run_id"] == started["run"]["run_id"])
    runtime.execute(run)
    final = read(setup)
    expected = "旧 hello 对象仍在内存中，但 s 不再引用它。" if name == "parenthesis" else narrowed
    assert final["run"]["status"] == "succeeded" and final["artifact"]["explanation"] == expected
    assert len(requests) == 2 and len(decisions) == 2
    assert requests[0]["review_mode"] == "atomic_answer_spans_v2"
    assert requests[1]["review_mode"] == "atomic_delta_spans_v2"
    assert requests[1]["candidate"]["evidence_ids"] == requests[0]["candidate"]["evidence_ids"]
    assert authority.reads.count("SEARCH") == 1
    public = json.dumps(read(setup, "EVENTS"))
    assert "atomic_assessments" not in public and "semantic_review" not in public
    with store.connect() as conn:
        events = conn.execute(
            "SELECT event_type, trace_detail FROM study_event WHERE run_id=%s ORDER BY sequence",
            (run["run_id"],),
        ).fetchall()
    revisions = [
        e["trace_detail"]["semantic_review"]
        for e in events
        if e["event_type"] == "node_started" and "semantic_review" in (e["trace_detail"] or {})
    ]
    assert len(revisions) == 1 and revisions[0]["revision_triggered"] is True
    assert any(c["supported"] is False for c in revisions[0]["claims"])


def test_fully_supported_multi_fact_claim_is_accepted_without_rewriting():
    b = body("The gate is open and a bell rings.", "The gate is open and a bell rings.")
    review = AtomicAnswerVerdict.model_validate(judgment(b), context=b).review()
    assert review.issues == [] and all(c.supported for c in review.atomic_assessments)


def test_atomic_telemetry_is_bounded_and_redacted(monkeypatch):
    secret = "private-atomic-secret-sentinel"
    monkeypatch.setenv("TEST_API_KEY", secret)
    detail = atomic_review_detail(
        "A until B.",
        [{"id": "a2", "supported": False, "evidence_ids": [secret] * 100}] * 100,
        revision_triggered=True,
    )
    assert len(detail["claims"]) == 24 and len(detail["claims"][0]["evidence_ids"]) == 8
    assert secret not in json.dumps(detail)
    assert len(json.dumps(detail).encode()) < 24 * 1024
    assert atomic_review_detail("A.", [{"id": ["a1"]}])["claims"] == []


def test_provider_rejects_stale_review_schema(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: CLIENT(
            transport=httpx.MockTransport(lambda r: response({"explanation_checks": []})), **kw
        ),
    )
    b = body("The gate is open.")
    with pytest.raises(ModelResponseError):
        ChatProvider("https://fixture.invalid/v1", "qwen3-max", "fixture-key").review(
            [{"role": "system", "content": "fixture"}, {"role": "user", "content": json.dumps(b)}], 10
        )
    assert review_schema("explanation", review_mode=b["review_mode"])["function"]["parameters"][
        "required"
    ] == ["goal_checks", "claim_checks"]


def judgment(b, rejected=()):
    result = _judgment(b, rejected)
    if b.get("relation_review"):
        claims = {c["id"]: c for c in b["atomic_claims"]}
        evidence = {e["evidence_id"]: e["text"] for e in b["evidence"]}
        for check in result["claim_checks"]:
            c = claims[check["id"]]
            text = c.get("source_text", b["candidate"]["explanation"][c.get("start", 0) : c.get("end", 0)])
            check["relation"] = {
                "source_relation": "rule",
                "gap": "none" if check["supported"] else "changed_scope",
                "claim_quote": text[:160],
                "grounds": [{"evidence_id": r, "quote": evidence[r][:240]} for r in check["evidence_ids"]],
            }
    return result
