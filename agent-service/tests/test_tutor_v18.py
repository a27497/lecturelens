"""Bounded usability diagnostics: protocol acceptance is not semantic quality."""

import json
import os
from pathlib import Path

import pytest
import test_tutor_v15 as legacy

from lecturelens_real_eval.tutor.contracts import Command
from lecturelens_real_eval.tutor.guarded_runtime import GuardedTutorRuntime
from lecturelens_real_eval.tutor.usable_runtime import (
    EVALUATION_LIMIT,
    OUTPUT_TOKENS,
    TEXT_LIMIT,
    UsableFinish,
    UsableTutorRuntime,
    render,
)

lab, offline = legacy.lab, legacy.offline
Provider, run = legacy.Provider, legacy.run


def retain(name, value):
    (Path(os.environ["TUTOR_USABILITY_OUTPUT"]) / (name + ".json")).write_text(
        json.dumps(value, indent=2, default=str, ensure_ascii=False) + "\n"
    )


def explain(
    body, text="A loop repeats its body for each item; changing the collection changes the number of visits."
):
    e = next(e for e in body["evidence"] if "once for each thing" in e["text"])
    return dict(
        kind="explanation", evidence_id=e["evidence_id"], quote="once for each thing in a sequence", text=text
    )


@pytest.fixture
def usable(lab):
    store, authority, _, scope = lab
    runtime = UsableTutorRuntime(store, authority)
    runtime.initialize()
    try:
        yield store, authority, runtime, scope
    finally:
        runtime.close()


def test_v17_rejects_supported_nonverbatim_explanation(lab):
    store, authority, _, scope = lab
    runtime = GuardedTutorRuntime(store, authority)
    runtime.initialize()
    provider = Provider(
        lambda b: dict(
            outcome="answered",
            blocks=[{k: v for k, v in {**explain(b), "kind": "source"}.items() if k != "quote"}],
        )
    )
    try:
        result = run((store, authority, runtime, scope), provider)
        retain("v17-normal-paraphrase-rejected", result)
        assert result["status"] == "failed" and result["error_code"] == "TUTOR_SUPPORT_INVALID"
    finally:
        runtime.close()


def test_supported_explanation_and_actual_request_contract(usable):
    provider = Provider(lambda b: dict(outcome="answered", blocks=[explain(b)]))
    result = run(usable, provider)
    assert result["status"] == "completed" and "repeats its body" in result["answer"]
    messages, schemas = provider.requests[-1]
    body = json.loads(messages[-1]["content"])
    assert body["rendering_limits"]["text"] == TEXT_LIMIT
    assert body["rendering_limits"]["evaluation"] == EVALUATION_LIMIT
    assert body["rendering_limits"]["output_tokens"] == OUTPUT_TOKENS
    assert "1600" not in messages[0]["content"] and "500" not in messages[0]["content"]
    assert (
        schemas[-1]["function"]["parameters"]["$defs"]["Explanation"]["properties"]["text"]["maxLength"]
        == 900
    )
    store, _, _, _ = usable
    with store.connect() as conn:
        reserved = conn.execute(
            "SELECT reserved_tokens FROM tutor_turn WHERE turn_id=%s", (result["turn_id"],)
        ).fetchone()["reserved_tokens"]
    assert reserved == sum(
        len(json.dumps([m, s], ensure_ascii=False).encode()) + OUTPUT_TOKENS for m, s in provider.requests
    )
    retain("normal-paraphrase", dict(result=result, messages=messages, schemas=schemas))


LONG_BLOCKS = [
    "A loop separates the operation from the number of items. The loop header selects each value from the collection in order, and the indented body applies the operation to that value. This explains why adding another item to the input does not require another copy of the print statement. The operation is written once, while the sequence determines how many times it is applied. This is an explanation of the supplied course example, rather than a claim that this code was executed here. The important boundary is the body: only statements at the loop's indentation level are repeated for each visit.",
    "Consider an explicit variation of the counting example: begin with length = 2 and names = ['Ada', 'Grace']. Before the first visit the counter is 2. Visiting Ada adds one, so the counter becomes 3. Visiting Grace adds one again, so it becomes 4. This is a conditional trace from the stated starting value and the loop rule, not an output copied from the original example, which uses different names and a different starting value. If the input collection changes, the number of updates changes too; the trace relies on exactly these two visits and one increment per visit.",
    "Here is the changed example, shown for reasoning rather than claimed execution:\n```python\nlength = 2\nnames = ['Ada', 'Grace']\nfor value in names:\n    length = length + 1  # one update per visited name\nprint(length)\n```\nThe last print is unindented, so it runs after the loop and observes the final counter. Moving it inside the loop would display the intermediate counters instead: first 3, then 4, under these assumptions. Changing indentation changes which observations are made, even when the increment operation and the final counter are unchanged.",
    "For indexing, distinguish selecting an item from iterating over a sequence. In the example names[0] selects the first name, Ada, under the explicitly supplied list above; names[1] selects Grace. A loop visits those values without needing a separate indexing expression for each item. Keep square brackets in Python subscription syntax: do not mechanically rewrite names[0] as names(0), which is outside the indexing form shown in this lesson. These are teaching examples to compare with the course's indexed-list and loop examples, not observations from a Python process or a claim about every possible object.",
]


def test_normal_long_explanation_code_conditions_and_tail_survive(usable):
    def finish(b):
        loop = explain(b)
        count = next(e for e in b["evidence"] if "length = 0" in e["text"])
        index = next(e for e in b["evidence"] if "by using `odds[0]`" in e["text"])
        return dict(
            outcome="answered",
            blocks=[
                loop | dict(text=LONG_BLOCKS[0]),
                loop
                | dict(text=LONG_BLOCKS[1], evidence_id=count["evidence_id"], quote="length = length + 1"),
                loop
                | dict(
                    text=LONG_BLOCKS[2],
                    evidence_id=count["evidence_id"],
                    quote="print('There are', length, 'names in the list.')",
                ),
                loop
                | dict(text=LONG_BLOCKS[3], evidence_id=index["evidence_id"], quote="by using `odds[0]`"),
            ],
        )

    provider = Provider(finish)
    original_decide = provider.decide

    def decide(messages, schemas, timeout):
        result = original_decide(messages, schemas, timeout)
        if result["name"] == "search_tutor_evidence":
            result["arguments"]["query"] = "loop length first index print odds"
        return result

    provider.decide = decide
    result = run(
        usable,
        provider,
        text="Explain the loop, trace length initially2 for Ada and Grace, compare inside/outside print, and show indexing and commented code.",
    )
    assert result["status"] == "completed" and 1600 < len(result["answer"]) <= TEXT_LIMIT
    assert "names[0]" in result["answer"] and "# one update" in result["answer"]
    assert "every possible object." in result["answer"] and len(result["citations"]) == 3
    store, _, runtime, scope = usable
    restored = runtime.command(Command(**scope, operation="GET"))["turns"][-1]
    assert restored["answer"] == result["answer"]
    calls = len(provider.requests)
    replay = runtime.command(
        Command(
            **scope,
            operation="TURN",
            client_turn_id="t1",
            text="Explain the loop, trace length initially2 for Ada and Grace, compare inside/outside print, and show indexing and commented code.",
        )
    )
    assert replay["replayed"] and len(provider.requests) == calls
    retain(
        "normal-long-teaching",
        dict(
            result=result,
            block_chars=[len(x) for x in LONG_BLOCKS],
            proposal=finish(json.loads(provider.requests[-1][0][-1]["content"])),
            rendered_chars=len(result["answer"]),
            requests=provider.requests,
        ),
    )


@pytest.mark.parametrize("char", ["a", "中", "😀", "\n"])
def test_schema_maxima_include_labels_full_ids_and_codepoints(char):
    proposal = UsableFinish.model_validate(
        dict(
            outcome="answered",
            blocks=[
                dict(kind="explanation", text=char * 900, evidence_id=str(n) * 64, quote="anchor")
                for n in range(4)
            ],
            evaluation_blocks=[
                dict(text=char * 384, evidence_id=str(n) * 64, learner_quote="reply", quote="anchor")
                for n in range(2)
            ],
        )
    )
    assert len(render([x.model_dump() for x in proposal.blocks])) <= TEXT_LIMIT
    assert (
        len(render([x.model_dump() for x in proposal.evaluation_blocks], feedback=True)) <= EVALUATION_LIMIT
    )


@pytest.mark.parametrize("repeat", [False, True])
def test_format_repair_once_preserves_full_draft(usable, repeat):
    provider = Provider(
        lambda b: dict(
            outcome="answered",
            blocks=[explain(b, "x" * (901 if repeat or "rejected_blocks" not in b else 900))],
        )
    )
    result = run(usable, provider)
    assert len(provider.requests) == 3
    body = json.loads(provider.requests[-1][0][-1]["content"])
    assert len(body["rejected_blocks"]["blocks"][0]["text"]) == 901
    assert result["status"] == ("failed" if repeat else "completed")
    if repeat:
        assert result["error_code"] == "TUTOR_FINISH_FORMAT_INVALID" and result["answer"] is None
    retain("format-repair-" + str(repeat), result)


@pytest.mark.parametrize(
    "attack", ["bad_anchor", "fabricated_id", "embedded_id", "calculation_comment", "false_source"]
)
def test_adversarial_binding_and_checked_expression_fail_closed(usable, attack):
    def finish(b):
        item = explain(b)
        if attack == "bad_anchor":
            item["quote"] = "not present in the source"
        if attack == "fabricated_id":
            item["evidence_id"] = "f" * 64
        if attack == "embedded_id":
            item["text"] += " [" + "f" * 64 + "]"
        if attack == "calculation_comment":
            item = {
                k: v
                for k, v in (
                    item | dict(kind="calculation", expression="2+2 # Every loop cures influenza.")
                ).items()
                if k != "text"
            }
        if attack == "false_source":
            item = {
                k: v
                for k, v in (item | dict(kind="source", text="Every loop cures influenza.")).items()
                if k != "quote"
            }
        return dict(outcome="answered", blocks=[item])

    result = run(usable, Provider(finish))
    assert result["status"] == "failed" and result["answer"] is None and not result["citations"]
    retain("adversarial-" + attack, result)


@pytest.mark.parametrize(
    "expression,expected", [("2+2", "4"), ("range(3)", "[0, 1, 2]"), ("[1,3,5]", "[1, 3, 5]")]
)
def test_positive_checked_values(usable, expression, expected):
    def finish(b):
        item = explain(b)
        return dict(
            outcome="answered",
            blocks=[
                dict(
                    kind="calculation",
                    evidence_id=item["evidence_id"],
                    quote=item["quote"],
                    expression=expression,
                )
            ],
        )

    result = run(usable, Provider(finish))
    assert result["status"] == "completed" and expression + " = " + expected in result["answer"]


def hint(b):
    item = explain(b)
    return dict(evidence_id=item["evidence_id"], quote=item["quote"], intent="trace_state")


def test_hint_then_real_feedback_history_and_learner_binding(usable):
    first = run(usable, Provider(lambda b: dict(outcome="socratic_prompt", hint=hint(b))), socratic=True)
    assert first["status"] == "completed" and "What changes at each step" in first["answer"]

    def finish(b):
        item = explain(b)
        return dict(
            outcome="answered",
            blocks=[item],
            evaluation_blocks=[
                dict(
                    evidence_id=item["evidence_id"],
                    quote=item["quote"],
                    learner_quote="one visit per item",
                    text="Your reply identifies one visit per item. Apply that condition to the two names before choosing the counter's final value.",
                )
            ],
        )

    provider = Provider(finish)
    second = run(usable, provider, key="t2", text="I expect one visit per item.")
    assert second["status"] == "completed" and "identifies one visit" in second["evaluation"]
    request = json.loads(provider.requests[-1][0][-1]["content"])
    assert request["history"][0]["answer"] == first["answer"]
    retain("normal-hint-and-history-feedback", dict(first=first, second=second, request=request))


@pytest.mark.parametrize("attack", ["free_solution", "wrong_learner"])
def test_socratic_and_feedback_adversaries(usable, attack):
    if attack == "free_solution":
        provider = Provider(
            lambda b: dict(
                outcome="socratic_prompt",
                hint=hint(b),
                blocks=[
                    explain(
                        b,
                        "Add seventy-five, twenty and two to obtain ninety-seven. Can you repeat these steps?",
                    )
                ],
            )
        )
        result = run(usable, provider, socratic=True)
    else:
        provider = Provider(
            lambda b: dict(
                outcome="answered",
                blocks=[explain(b)],
                evaluation_blocks=[
                    dict(
                        text="You are correct",
                        learner_quote="I never said this",
                        quote=explain(b)["quote"],
                        evidence_id=explain(b)["evidence_id"],
                    )
                ],
            )
        )
        result = run(usable, provider)
    assert result["status"] == "failed" and result["answer"] is None
    retain("adversarial-" + attack, result)


def test_insufficient_is_exact_and_not_a_blanket_refusal(usable):
    result = run(usable, Provider(lambda b: dict(outcome="insufficient_evidence")))
    assert (
        result["status"] == "completed"
        and result["outcome"] == "insufficient_evidence"
        and not result["citations"]
    )
    retain("normal-insufficient", result)


def test_residual_semantic_false_claim_is_not_deterministically_detected(usable):
    result = run(
        usable,
        Provider(lambda b: dict(outcome="answered", blocks=[explain(b, "Every loop cures influenza.")])),
    )
    assert result["status"] == "completed" and "cures influenza" in result["answer"]
    retain(
        "RESIDUAL-unsupported-explanation-NOT-QUALITY-PASS",
        dict(
            result=result,
            verdict="UNSUPPORTED_CONTENT_ACCEPTED; semantic judgment remains unresolved; not a successful tutoring case",
        ),
    )


def test_late_cancel_records_known_usage_without_publication(usable):
    store, _, runtime, scope = usable
    provider = Provider(lambda b: dict(outcome="answered", blocks=[explain(b)]))
    original = provider.decide

    def decide(messages, schemas, timeout):
        result = original(messages, schemas, timeout)
        if result["name"] == "finish_tutor_turn":
            runtime.command(Command(**scope, operation="CANCEL", client_turn_id="t1"))
        return result

    provider.decide = decide
    result = run(usable, provider)
    assert result["status"] == "cancelled" and result["answer"] is None
    with store.connect() as conn:
        row = conn.execute("SELECT checkpoint FROM tutor_turn WHERE client_turn_id='t1'").fetchone()
    assert row["checkpoint"]["call_accounting"][-1]["usage_state"] == "known"
    retain("cancel-with-late-usage", dict(result=result, checkpoint=row["checkpoint"]))


def test_targeted_socratic_hint_keeps_pedagogy_without_solution(usable):
    provider = Provider(lambda b: dict(outcome="socratic_prompt", hint=hint(b) | dict(intent="locate_body")))
    result = run(usable, provider, socratic=True)
    assert result["status"] == "completed"
    assert "Which lines belong to the indented loop body" in result["answer"]
    assert "length =" not in result["answer"] and " = 4" not in result["answer"]
    retain("normal-targeted-hint", result)


def test_smoke_policy_cannot_raise_output_requests_or_liability():
    from lecturelens_real_eval.tutor.usable_policy import UsablePolicy
    from lecturelens_real_eval.tutor_channel import EvalError

    UsablePolicy().validate()
    for args in [
        dict(max_tokens=4097),
        dict(max_calls=13),
        dict(max_nano_usd=300000001),
        dict(model="other"),
        dict(max_tokens=True),
    ]:
        with pytest.raises(EvalError):
            UsablePolicy(**args).validate()


def test_smoke_reservation_hard_limit_before_thirteenth_send(usable):
    from lecturelens_real_eval.tutor.usable_policy import UsablePolicy
    from lecturelens_real_eval.tutor_channel import EvalError, Ledger

    store, _, _, _ = usable
    path = Path(os.environ["TUTOR_USABILITY_OUTPUT"]) / "twelve-cap-ledger.jsonl"
    ledger = Ledger(store.dsn, path, "v18-limit-mechanism", UsablePolicy())
    ledger.install()
    for _ in range(12):
        reservation = ledger.reserve(
            json.dumps(
                {"model": "deepseek-flash", "tools": [{"function": {"name": "finish_tutor_turn"}}]}
            ).encode(),
            OUTPUT_TOKENS,
        )
        ledger.settle(reservation, {"prompt_tokens": 1, "completion_tokens": 1}, None)
    with pytest.raises(EvalError, match="BUDGET_EXHAUSTED"):
        ledger.reserve(
            json.dumps(
                {"model": "deepseek-flash", "tools": [{"function": {"name": "finish_tutor_turn"}}]}
            ).encode(),
            OUTPUT_TOKENS,
        )
    assert ledger.check()["calls"] == 12


def test_smoke_invalid_grant_cannot_expand_scope(tmp_path):
    from datetime import datetime, timedelta, timezone

    from lecturelens_real_eval.tutor.usable_smoke import live_admission
    from lecturelens_real_eval.tutor_channel import EvalError

    state = dict(candidate_sha256="a" * 64, packet_sha256="b" * 64)
    grant = dict(
        authorized=True,
        scope="ONE_V18_THREE_TURN_SMOKE_NO_RETRY_NO_EXPANSION",
        **state,
        model="deepseek-flash",
        max_output_tokens=4096,
        max_requests=12,
        max_nano_usd=300000000,
        expires_utc=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        run_id="v18-synthetic-test-only",
    )
    price = dict(
        requested_model="deepseek-flash",
        configuration_available_verified=True,
        input_nano_usd_per_token=300,
        output_nano_usd_per_token=1200,
        official_source="https://api-docs.deepseek.com/quick_start/pricing/",
        reviewed_utc=datetime.now(timezone.utc).isoformat(),
        no_cache_peak_rates_cover_current_prices=True,
    )
    gp, pp = tmp_path / "grant.json", tmp_path / "pricing.json"
    pp.write_text(json.dumps(price))
    for change in [
        dict(max_requests=13),
        dict(max_nano_usd=300000001),
        dict(max_output_tokens=4097),
        dict(scope="ONE_V17_DIAGNOSTIC_NO_RETRY_NO_EXPANSION"),
    ]:
        gp.write_text(json.dumps(grant | change))
        with pytest.raises(EvalError, match="RECEIPTS_INVALID"):
            live_admission(state, gp, pp)


def test_frozen_entry_default_and_unapproved_live_have_no_output(tmp_path):
    from lecturelens_real_eval.tutor.usable_smoke import execute, verify_inputs
    from lecturelens_real_eval.tutor_channel import EvalError

    result = verify_inputs()
    assert not result["ready_for_live"] and len(result["blockers"]) == 2
    with pytest.raises(EvalError, match="RECEIPTS_REQUIRED"):
        execute(tmp_path / "not-created", live=True)
    assert not (tmp_path / "not-created").exists()


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "format_once",
        "format_twice",
        "malformed",
        "unknown_usage",
        "model_mismatch",
        "fabricated_id",
        "support_invalid",
        "budget",
    ],
)
def test_frozen_smoke_actual_entry_and_wire(fault):
    from lecturelens_real_eval.tutor.usable_smoke import execute

    output = Path(os.environ["TUTOR_USABILITY_OUTPUT"]) / ("entry-" + fault)
    result = execute(output, fault=fault)
    assert result["real_model_calls"] == 0 and result["cost_usd"] == "0" and result["quality"] == "NOT_RUN"
    assert result["sent_requests"] == result["ledger"]["calls"]
    if fault in {"none", "format_once"}:
        assert (result["completed"], result["failed"], result["skipped"], result["sent_requests"]) == (
            3,
            0,
            0,
            6 if fault == "none" else 8,
        )
    else:
        assert (result["completed"], result["failed"], result["skipped"]) == (0, 1, 2)
        assert result["global_stop"]
    for path in (output / "wire").glob("*-request.body"):
        wire = json.loads(path.read_bytes())
        assert wire["model"] == "deepseek-flash" and wire["max_tokens"] == OUTPUT_TOKENS
        assert wire["temperature"] == 0 and wire["thinking"] == {"type": "disabled"}
        assert not any(key in path.read_text() for key in ["reference_points", "scoring", "ambiguities"])
        assert path.with_name(path.name.replace("request.body", "response.body")).is_file()
    if fault in {"malformed", "unknown_usage"}:
        ledger = [json.loads(line) for line in (output / "ledger.jsonl").read_text().splitlines()]
        assert (
            ledger[-1]["usage"] is None and ledger[-1]["charged_nano_usd"] >= ledger[0]["reserved_nano_usd"]
        )
    retain("entry-" + fault + "-result", result)


def test_no_positive_retrieval_yields_explicit_insufficient_without_fabricated_sources(usable):
    from lecturelens_real_eval.tutor.relevant_authority import RelevantSnapshotAuthority

    _, authority, runtime, scope = usable
    relevant = RelevantSnapshotAuthority(authority.snapshot)
    relevant.register(scope, "carpentries-python")
    runtime.authority = relevant
    provider = Provider(lambda b: dict(outcome="insufficient_evidence"))
    original = provider.decide

    def decide(messages, schemas, timeout):
        result = original(messages, schemas, timeout)
        if result["name"] == "search_tutor_evidence":
            result["arguments"]["query"] = "zzzxxyyqq"
        return result

    provider.decide = decide
    result = run(usable, provider, text="A topic absent from these excerpts")
    assert result["status"] == "completed" and result["outcome"] == "insufficient_evidence"
    body = json.loads(provider.requests[-1][0][-1]["content"])
    assert not body["evidence"] and body["observations"][0]["no_positive_match"]
    assert not result["citations"]
    retain("normal-no-hit-insufficient", dict(result=result, request=body))
