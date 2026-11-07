"""V19 protocol and complete authored teaching fixtures; no new model quality claim."""

import copy
import json
import os
from pathlib import Path

import pytest
import test_tutor_v15 as legacy
import test_tutor_v18 as teaching

from lecturelens_real_eval.tutor.contracts import Command
from lecturelens_real_eval.tutor.relevant_authority import RelevantSnapshotAuthority
from lecturelens_real_eval.tutor.selection_runtime import SelectedTutorRuntime, source_hash, units

lab, offline = legacy.lab, legacy.offline
run = legacy.run
ROOT = Path(__file__).resolve().parents[2]


def retain(name, value):
    (Path(os.environ["TUTOR_SELECTION_OUTPUT"]) / (name + ".json")).write_text(
        json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n"
    )


def raw(e):
    return "".join(text for _, text in e["source_units"])


def span(body, needle, *, full=False):
    e = next(e for e in body["evidence"] if needle in raw(e))
    matching = next(n for n, text in e["source_units"] if needle in text)
    return dict(
        evidence_id=e["evidence_id"],
        first_unit=1 if full else matching,
        last_unit=len(e["source_units"]) if full else matching,
    )


def explanation(body, text="A loop applies its body once per item in the supplied sequence."):
    return dict(kind="explanation", span=span(body, "once for each thing"), text=text)


class Provider:
    def __init__(self, finish, *, second_search=False):
        self.finish, self.second_search, self.requests = finish, second_search, []

    def decide(self, messages, schemas, timeout):
        self.requests.append(copy.deepcopy((messages, schemas)))
        b = json.loads(messages[-1]["content"])
        searches = sum(o["tool"] == "search_tutor_evidence" for o in b["observations"])
        if not searches or self.second_search and searches == 1 and len(b["observations"]) == 1:
            return dict(
                name="search_tutor_evidence",
                arguments=dict(query="loop length first index print odds"),
                usage=dict(prompt_tokens=100, completion_tokens=20),
            )
        return dict(
            name="finish_tutor_turn",
            arguments=self.finish(b),
            usage=dict(prompt_tokens=100, completion_tokens=60),
        )


@pytest.fixture
def selected(lab):
    store, authority, _, scope = lab
    runtime = SelectedTutorRuntime(store, authority)
    runtime.initialize()
    try:
        yield store, authority, runtime, scope
    finally:
        runtime.close()


@pytest.mark.parametrize(
    "text",
    [
        "x" * 1001,
        "中😀" * 700,
        "```python\r\nvalues = ['a', 'b']\r\nprint(values[0]) # comment\r\n```\r\n",
        "line\n" * 900,
    ],
)
def test_units_are_lossless_bounded_codepoints(text):
    parts = units(text)
    assert "".join(s for _, s in parts) == text
    assert all(len(s) <= 200 for _, s in parts)
    assert [n for n, _ in parts] == list(range(1, len(parts) + 1))


def complete(body):
    return dict(
        outcome="answered",
        blocks=[
            explanation(body, teaching.LONG_BLOCKS[0]),
            dict(
                kind="explanation",
                span=span(body, "length = length + 1"),
                text=teaching.LONG_BLOCKS[1],
            ),
            dict(
                kind="explanation",
                span=span(body, "length = length + 1"),
                text=teaching.LONG_BLOCKS[2],
            ),
            dict(
                kind="explanation",
                span=span(body, "by using `odds[0]`", full=True),
                text=teaching.LONG_BLOCKS[3],
            ),
        ],
    )


def test_complete_teaching_preserves_code_conditions_index_tail_and_bindings(selected):
    provider = Provider(complete)
    result = run(
        selected,
        provider,
        text="Explain loops, trace the changed counter, provide commented Python, compare printing and indexing.",
    )
    assert result["status"] == "completed"
    for text in teaching.LONG_BLOCKS:
        assert text in result["answer"]
    assert len(result["answer"]) == 2721 and len(result["citations"]) == 3
    store, authority, runtime, scope = selected
    with store.connect() as conn:
        checkpoint = conn.execute(
            "SELECT checkpoint FROM tutor_turn WHERE turn_id=%s", (result["turn_id"],)
        ).fetchone()["checkpoint"]
    assert checkpoint["candidate"] == "p8-tutor-selected-v19-development"
    assert len(checkpoint["resolved_spans"]) == 4
    for item in checkpoint["resolved_spans"]:
        source = next(e["text"] for e in result["citations"] if e["evidence_id"] == item["evidence_id"])
        assert source_hash(source) == item["source_sha256"]
        assert source_hash(source[item["start_codepoint"] : item["end_codepoint"]]) == item["span_sha256"]
    restored = SelectedTutorRuntime(store, authority).command(Command(**scope, operation="GET"))["turns"][-1]
    assert restored == result
    retain(
        "complete-authored-teaching",
        dict(
            result=result,
            requests=provider.requests,
            checkpoint=checkpoint,
            quality="AUTHORED_FIXTURE_NOT_MODEL_GENERATION",
        ),
    )


def test_selected_markdown_is_never_retyped_or_normalized(selected):
    provider = Provider(
        lambda b: dict(
            outcome="answered",
            blocks=[dict(kind="source", span=span(b, "once for each thing") | dict(first_unit=1))],
        )
    )
    result = run(selected, provider)
    assert result["status"] == "completed"
    body = json.loads(provider.requests[-1][0][-1]["content"])
    selection = span(body, "once for each thing") | dict(first_unit=1)
    e = next(e for e in body["evidence"] if e["evidence_id"] == selection["evidence_id"])
    original = "".join(
        t for n, t in e["source_units"] if selection["first_unit"] <= n <= selection["last_unit"]
    )
    assert "[for loop](../learners/reference.md#for-loop)" in original
    assert original in result["answer"]
    assert all("source_sha256" not in e for e in body["evidence"])
    assert all("text" not in e for e in body["evidence"])
    assert "evidence_indices" in body["observations"][0] and "evidence_ids" not in body["observations"][0]
    retain("selected-markdown-publication", dict(result=result, request=body))


@pytest.mark.parametrize(
    "first,second", [("span", "format"), ("format", "span"), ("span", None), ("format", None)]
)
def test_one_shared_finish_correction_after_two_searches(selected, first, second):
    def finish(b):
        value = explanation(b)
        mode = second if "rejected_blocks" in b else first
        if mode == "span":
            value["span"]["last_unit"] = 7999
        if mode == "format":
            value["text"] = "x" * 901
        return dict(outcome="answered", blocks=[value])

    provider = Provider(finish, second_search=True)
    result = run(selected, provider)
    assert len(provider.requests) == 4
    assert result["status"] == ("completed" if second is None else "failed")
    if second is not None:
        assert result["error_code"] == "TUTOR_SHARED_FINISH_CORRECTION_INVALID"
    store, _, _, _ = selected
    with store.connect() as conn:
        row = conn.execute(
            "SELECT checkpoint,reserved_tokens FROM tutor_turn WHERE turn_id=%s", (result["turn_id"],)
        ).fetchone()
    observations = [
        o for o in row["checkpoint"]["observations"] if o.get("error") == "TUTOR_FINISH_REPAIR_REQUIRED"
    ]
    assert len(observations) == 1 and row["reserved_tokens"] <= 64000
    assert [s["function"]["name"] for s in provider.requests[-1][1]] == ["finish_tutor_turn"]
    retain(
        "shared-" + first + "-" + str(second),
        dict(result=result, checkpoint=row["checkpoint"], requests=provider.requests),
    )


@pytest.mark.parametrize(
    "attack",
    [
        "unknown_id",
        "embedded_id",
        "negative_unit",
        "reverse_units",
        "extra_source_text",
        "calculation_comment",
        "socratic_solution",
        "wrong_learner",
    ],
)
def test_adversarial_boundaries(selected, attack):
    def finish(b):
        value = explanation(b)
        result = dict(outcome="answered", blocks=[value])
        if attack == "unknown_id":
            value["span"]["evidence_id"] = "f" * 64
        if attack == "embedded_id":
            value["text"] += " [" + "f" * 64 + "]"
        if attack == "negative_unit":
            value["span"]["first_unit"] = -1
        if attack == "reverse_units":
            value["span"].update(first_unit=2, last_unit=1)
        if attack == "extra_source_text":
            value["kind"] = "source"
        if attack == "calculation_comment":
            value = dict(
                kind="calculation", span=value["span"], expression="2+2 # Every loop cures influenza."
            )
            result["blocks"] = [value]
        if attack == "socratic_solution":
            result.update(outcome="socratic_prompt", hint=dict(span=value["span"], intent="locate_body"))
            value["text"] = "The complete answer is ninety-seven. Can you repeat it?"
        if attack == "wrong_learner":
            result["evaluation_blocks"] = [
                dict(span=value["span"], text="You are correct", learner_quote="I never said this")
            ]
        return result

    provider = Provider(finish)
    result = run(selected, provider, socratic=attack == "socratic_solution")
    assert result["status"] == "failed" and result["answer"] is None and not result["citations"]
    assert len(provider.requests) <= 3
    retain("adversarial-" + attack, result)


def test_hint_feedback_complete_history_and_idempotency(selected):
    first = run(
        selected,
        Provider(
            lambda b: dict(
                outcome="socratic_prompt",
                hint=dict(span=span(b, "length = length + 1"), intent="locate_body"),
            )
        ),
        socratic=True,
    )
    assert first["status"] == "completed" and "Which lines belong" in first["answer"]

    def finish(b):
        value = complete(b)
        value["evaluation_blocks"] = [
            dict(
                span=span(b, "length = length + 1"),
                learner_quote="only once",
                text="Your reply assumes one update total. There are two names, so the increment runs twice; the unindented print is after the loop. Under the stated start2, the changes are2 to3 to4.",
            )
        ]
        return value

    provider = Provider(finish)
    second = run(selected, provider, key="t2", text="I think it changes only once and the print is inside.")
    assert second["status"] == "completed" and "two names" in second["evaluation"]
    body = json.loads(provider.requests[-1][0][-1]["content"])
    assert body["history"][0]["answer"] == first["answer"]
    _, _, runtime, scope = selected
    replay = runtime.command(
        Command(
            **scope,
            operation="TURN",
            client_turn_id="t2",
            text="I think it changes only once and the print is inside.",
        )
    )
    assert replay["replayed"] and len(provider.requests) == 2
    retain("hint-feedback-history", dict(first=first, second=second, request=body))


def test_no_hit_is_insufficient_without_sources(selected):
    _, authority, runtime, scope = selected
    relevant = RelevantSnapshotAuthority(authority.snapshot)
    relevant.register(scope, "carpentries-python")
    runtime.authority = relevant
    provider = Provider(lambda b: dict(outcome="insufficient_evidence"))
    original = provider.decide

    def decide(*args):
        value = original(*args)
        if value["name"] == "search_tutor_evidence":
            value["arguments"]["query"] = "zzzyyxxqq"
        return value

    provider.decide = decide
    result = run(selected, provider)
    assert (
        result["status"] == "completed"
        and result["outcome"] == "insufficient_evidence"
        and not result["citations"]
    )


def test_a03_valid_selected_anchor_does_not_prove_semantics(selected):
    result = run(
        selected,
        Provider(lambda b: dict(outcome="answered", blocks=[explanation(b, "Every loop cures influenza.")])),
    )
    assert result["status"] == "completed" and "cures influenza" in result["answer"]
    retain(
        "RESIDUAL-A03-not-a-quality-pass",
        dict(
            result=result, verdict="KNOWN_UNSUPPORTED_INTERPRETATION_ACCEPTED; selection proves binding only"
        ),
    )


def test_late_cancel_keeps_known_usage_and_no_publication(selected):
    store, _, runtime, scope = selected
    provider = Provider(lambda b: dict(outcome="answered", blocks=[explanation(b)]))
    original = provider.decide

    def decide(*args):
        response = original(*args)
        if response["name"] == "finish_tutor_turn":
            runtime.command(Command(**scope, operation="CANCEL", client_turn_id="t1"))
        return response

    provider.decide = decide
    result = run(selected, provider)
    assert result["status"] == "cancelled" and result["answer"] is None
    with store.connect() as conn:
        state = conn.execute(
            "SELECT checkpoint FROM tutor_turn WHERE turn_id=%s", (result["turn_id"],)
        ).fetchone()["checkpoint"]
    assert state["call_accounting"][-1]["usage_state"] == "known"


def test_historical_three_raw_responses_then_authored_fourth_correction(selected):
    store, authority, runtime, scope = selected
    relevant = RelevantSnapshotAuthority(authority.snapshot)
    relevant.register(scope, "carpentries-python")
    runtime.authority = relevant
    captured = ROOT / ".data/tutor-v18-live-20261107/run/wire"
    provider = Provider(complete)

    def decide(messages, schemas, timeout):
        provider.requests.append(copy.deepcopy((messages, schemas)))
        n = len(provider.requests)
        if n <= 3:
            response = json.loads((captured / f"{n:03d}-response.body").read_bytes())
            calls = response["choices"][0]["message"]["tool_calls"]
            item = calls[0]["function"]
            return dict(
                name=item["name"],
                arguments=json.loads(item["arguments"]),
                usage={k: response["usage"][k] for k in ["prompt_tokens", "completion_tokens"]},
                dropped_tool_calls=len(calls) - 1,
            )
        return dict(
            name="finish_tutor_turn",
            arguments=complete(json.loads(messages[-1]["content"])),
            usage=dict(prompt_tokens=100, completion_tokens=60),
        )

    provider.decide = decide
    result = run(selected, provider)
    assert result["status"] == "completed" and len(provider.requests) == 4
    with store.connect() as conn:
        row = conn.execute(
            "SELECT checkpoint,reserved_tokens FROM tutor_turn WHERE turn_id=%s", (result["turn_id"],)
        ).fetchone()
    assert row["reserved_tokens"] <= 64000
    for text in teaching.LONG_BLOCKS:
        assert text in result["answer"]
    retain(
        "historical-raw-response-replay-authored-correction",
        dict(
            result=result,
            checkpoint=row["checkpoint"],
            reserved_proxy=row["reserved_tokens"],
            requests=provider.requests,
            replay="THREE_RETAINED_ORIGINAL_RESPONSE_BODIES_PARSED; NEW_REQUEST_SCHEMA; FOURTH_IS_AUTHORED_MOCK_NOT_MODEL_SUCCESS",
        ),
    )


def test_authored_commented_python_fixture_is_executable_and_retained(selected):
    import subprocess

    code = teaching.LONG_BLOCKS[2].split("```python\n", 1)[1].split("```", 1)[0]
    # This is fixed authored test code, never untrusted model-generated execution.
    result = subprocess.run(
        [str(ROOT / "agent-service/.venv/bin/python"), "-I", "-S", "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == "4\n"
    provider = Provider(complete)
    saved = run(selected, provider)
    assert saved["status"] == "completed" and code in saved["answer"]


@pytest.mark.parametrize("when", ["return", "publication"])
def test_same_id_changed_source_is_rejected_again_at_publication(selected, when):
    _, authority, _, _ = selected
    original = authority.read
    armed = [False]
    reads = [0]

    def read(scope, action="CHECK", **args):
        result = original(scope, action, **args)
        if armed[0] and action == "READ":
            reads[0] += 1
            if reads[0] == (1 if when == "return" else 3):
                result = copy.deepcopy(result)
                result["evidence"][0]["text"] += "\nChanged without a revision bump."
        return result

    authority.read = read

    def finish(b):
        value = dict(outcome="answered", blocks=[explanation(b)])
        armed[0] = True
        return value

    provider = Provider(finish)
    result = run(selected, provider)
    assert result["status"] == "failed" and result["error_code"] == "TUTOR_SELECTED_SOURCE_CHANGED"
    assert result["answer"] is None and len(provider.requests) == 2
    retain("source-fence-" + when, result)


@pytest.mark.parametrize("changed", [False, True])
def test_prepaid_shared_correction_restart_reuses_reservation_and_fences_sources(selected, changed):
    store, authority, runtime, scope = selected
    provider = Provider(
        lambda b: dict(
            outcome="answered",
            blocks=[
                explanation(b)
                | (
                    {}
                    if "rejected_blocks" in b
                    else {"span": span(b, "once for each thing") | dict(last_unit=7999)}
                )
            ],
        ),
        second_search=True,
    )
    runtime.provider = provider
    runtime.command(Command(**scope, operation="TURN", client_turn_id="t1", text="Explain loops"))
    candidate = store.candidates()[0]
    original = runtime.repair

    class PausedAfterReservation(Exception):
        pass

    def pause(*args, **kwargs):
        original(*args, **kwargs)
        raise PausedAfterReservation()

    runtime.repair = pause
    with pytest.raises(PausedAfterReservation):
        runtime.loop(candidate["turn_id"])
    assert len(provider.requests) == 3
    with store.connect() as conn:
        before = conn.execute(
            "SELECT model_calls,reserved_tokens,checkpoint FROM tutor_turn WHERE turn_id=%s",
            (candidate["turn_id"],),
        ).fetchone()
    assert before["model_calls"] == 4 and before["checkpoint"]["repair_request"]
    assert before["checkpoint"]["call_accounting"][-1]["response_state"] == "prepaid_not_dispatched"
    if changed:
        old = authority.read

        def read(scope, action="CHECK", **args):
            result = old(scope, action, **args)
            if action == "READ" and result["evidence"]:
                result = copy.deepcopy(result)
                result["evidence"][0]["text"] += "\nChanged after reservation."
            return result

        authority.read = read
    resumed = SelectedTutorRuntime(store, authority, provider)
    try:
        resumed.execute(candidate)
        result = resumed.command(Command(**scope, operation="GET"))["turns"][-1]
    finally:
        resumed.close()
    assert result["status"] == ("failed" if changed else "completed")
    assert len(provider.requests) == (3 if changed else 4)
    with store.connect() as conn:
        after = conn.execute(
            "SELECT model_calls,reserved_tokens,checkpoint FROM tutor_turn WHERE turn_id=%s",
            (candidate["turn_id"],),
        ).fetchone()
    assert (
        after["model_calls"] == before["model_calls"]
        and after["reserved_tokens"] == before["reserved_tokens"]
    )
    if changed:
        assert result["error_code"] == "TUTOR_SELECTED_SOURCE_CHANGED"
    retain("prepaid-restart-" + str(changed), dict(result=result, before=before, after=after))


def test_shared_correction_still_fails_before_egress_when_token_budget_exhausted(selected):
    store, _, _, scope = selected

    def finish(b):
        with store.connect() as conn:
            conn.execute(
                "UPDATE tutor_session SET max_tokens=reserved_tokens WHERE session_id=%s",
                (scope["session_id"],),
            )
        return dict(
            outcome="answered",
            blocks=[explanation(b) | dict(span=span(b, "once for each thing") | dict(last_unit=7999))],
        )

    provider = Provider(finish)
    result = run(selected, provider)
    assert result["status"] == "failed" and result["error_code"] == "TUTOR_REPAIR_BUDGET_UNAVAILABLE"
    assert len(provider.requests) == 2 and result["answer"] is None
    retain("shared-correction-no-budget", result)


def test_frozen_entry_default_is_read_only_and_live_needs_new_receipts():
    from lecturelens_real_eval.tutor.selection_smoke import execute, verify_inputs
    from lecturelens_real_eval.tutor_channel import EvalError

    state = verify_inputs()
    assert state["real_calls"] == 0 and not state["ready_for_live"]
    output = Path(os.environ["TUTOR_SELECTION_OUTPUT"]) / "unauthorized-live"
    with pytest.raises(EvalError, match="V19_LIVE_RECEIPTS_REQUIRED"):
        execute(output, live=True)
    assert not output.exists()


@pytest.mark.parametrize(
    "fault,completed,failed,skipped,sends",
    [
        ("none", 3, 0, 0, 6),
        ("span_once", 3, 0, 0, 9),
        ("format_once", 3, 0, 0, 8),
        ("span_twice", 0, 1, 2, 3),
        ("format_twice", 0, 1, 2, 3),
        ("fabricated_id", 0, 1, 2, 2),
        ("malformed", 0, 1, 2, 1),
        ("unknown_usage", 0, 1, 2, 1),
        ("model_mismatch", 0, 1, 2, 1),
        ("budget", 0, 1, 2, 1),
    ],
)
def test_frozen_actual_entry_captures_and_stops(fault, completed, failed, skipped, sends):
    from lecturelens_real_eval.tutor.selection_smoke import execute

    output = Path(os.environ["TUTOR_SELECTION_OUTPUT"]) / ("entry-" + fault)
    summary = execute(output, fault=fault)
    assert [summary[k] for k in ("completed", "failed", "skipped", "sent_requests")] == [
        completed,
        failed,
        skipped,
        sends,
    ]
    assert summary["real_model_calls"] == 0 and summary["quality"] == "NOT_RUN"
    assert len(list((output / "wire").glob("*-request.body"))) == sends
    assert (output / "ledger.jsonl").exists() and (output / "runtime.json").exists()
    if fault in {"unknown_usage", "malformed"}:
        assert summary["ledger"]["pending"] == 0
        # Unknown settlements retain a positive liability; they are never zero.
        assert summary["ledger"]["nano_usd"] > 0


def test_frozen_http_entry_replays_original_response_bodies_then_authored_correction():
    from lecturelens_real_eval.tutor.selection_smoke import execute

    bodies = sorted((ROOT / ".data/tutor-v18-live-20261107/run/wire").glob("*-response.body"))
    assert len(bodies) == 3
    payloads = [p.read_bytes() for p in bodies]

    def reply(wire, index):
        if index <= 3:
            return payloads[index - 1]
        if index == 4:
            response = json.loads(payloads[2])
            response["usage"] = dict(prompt_tokens=100, completion_tokens=60)
            response["choices"][0]["message"]["tool_calls"] = [
                dict(
                    type="function",
                    function=dict(
                        name="finish_tutor_turn",
                        arguments=json.dumps(complete(json.loads(wire["messages"][-1]["content"]))),
                    ),
                )
            ]
            return json.dumps(response).encode()
        return None

    output = Path(os.environ["TUTOR_SELECTION_OUTPUT"]) / "entry-historical-response-replay"
    summary = execute(output, mock_response=reply)
    assert summary["completed"] == 3 and summary["sent_requests"] == 8
    captured = sorted((output / "wire").glob("*-response.body"))
    assert [p.read_bytes() for p in captured[:3]] == payloads
    outcomes = json.loads((output / "outcomes.json").read_bytes())
    assert len(outcomes[0]["answer"]) == 2721
    assert all(text in outcomes[0]["answer"] for text in teaching.LONG_BLOCKS)
    assert summary["real_model_calls"] == 0
    retain(
        "http-replay-disclosure",
        dict(
            first_three="ORIGINAL_RETAINED_RESPONSE_ENTITY_BYTES_UNCHANGED_UNDER_NEW_REQUEST_SCHEMA",
            fourth="AUTHORED_COMPLETE_MOCK_CORRECTION_NOT_REAL_GENERATION_SUCCESS",
            last_two_turns="DEFAULT_MOCK_MECHANICS_NOT_TEACHING_QUALITY",
            summary=summary,
        ),
    )
