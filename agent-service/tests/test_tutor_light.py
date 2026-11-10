"""Authored/offline teaching and actual PostgreSQL boundaries, never quality PASS."""

import hashlib
import json
import os
import uuid
import zipfile
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from test_tutor import Authority, command, offline, run, submit  # noqa: F401

from lecturelens_agent.study.store import StudyError
from lecturelens_real_eval.tutor.contracts import ABSTENTION, ANSWER_MAX_CHARS, Command
from lecturelens_real_eval.tutor.light import SYSTEM, LightTutorRuntime, source_only
from lecturelens_real_eval.tutor.store import TutorStore


class Authored:
    def __init__(self):
        self.requests = []
        self.text = "BFS reaches a vertex in the earliest frontier because every step adds one edge. Thus its level equals its shortest unweighted distance [e1]."
        self.hook = None

    def complete(self, messages, schema, timeout):
        data = json.loads(messages[-1]["content"])
        self.requests.append(data)
        if self.hook:
            return self.hook(data)
        return dict(
            outcome="answered", text=self.text, focus="", usage={"prompt_tokens": 90, "completion_tokens": 70}
        )


@pytest.fixture
def lab(request):
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    schema = "light_" + uuid.uuid4().hex
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    store = TutorStore(make_conninfo(dsn, options=f"-csearch_path={schema},public"), engine="light")
    scope = dict(owner_id=801, course_id="light-" + uuid.uuid4().hex, revision=1)
    authority = Authority(scope.copy())
    runtime = LightTutorRuntime(store, authority, Authored())
    runtime.initialize()
    scope["session_id"] = runtime.command(Command(**scope, operation="CREATE", request_key="s"))["session"][
        "session_id"
    ]
    yield store, authority, runtime, scope
    runtime.close()
    if os.environ.get("PHASE1D_EVIDENCE_DIR"):
        with store.connect() as conn:
            records = {
                "kind": "OFFLINE_AUTHORED_MECHANISM_ONLY",
                "test": request.node.name,
                "sessions": conn.execute("SELECT * FROM tutor_session ORDER BY created_at").fetchall(),
                "turns": conn.execute("SELECT * FROM tutor_turn ORDER BY ordinal").fetchall(),
                "provider_inputs": runtime.provider.requests,
            }
        target = Path(os.environ["PHASE1D_EVIDENCE_DIR"]) / f"{schema}.json"
        target.write_text(json.dumps(records, ensure_ascii=False, default=str, indent=2) + "\n")
        target.chmod(0o600)
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def checkpoint(lab):
    with lab[0].connect() as conn:
        return conn.execute("SELECT checkpoint FROM tutor_turn ORDER BY ordinal DESC LIMIT 1").fetchone()[
            "checkpoint"
        ]


def test_one_generation_full_answer_canonical_source_replay_and_restart(lab):
    result = run(lab)
    assert result["status"] == "completed" and result["answer"] == lab[2].provider.text
    assert result["model_calls"] == 1 and len(result["usage"]) == 1
    assert result["reserved_tokens"] < 64000 and result["tool_calls"] == 1
    assert result["citations"] == lab[1].read(lab[3], "READ")["evidence"]
    assert submit(lab)["replayed"]
    restored = LightTutorRuntime(TutorStore(lab[0].dsn, engine="light"), lab[1], Authored())
    assert restored.command(Command(**lab[3], operation="GET"))["turns"] == [result]
    restored.execute(dict(turn_id=result["turn_id"], session_id=lab[3]["session_id"]))
    assert not restored.provider.requests


def test_complete_multipart_code_and_indices_are_not_truncated(lab):
    # Frozen failure subject is a test fixture, never a product-specific rule.
    text = """A loop avoids duplicated indexed prints and handles list lengths consistently [e1].
For your changed example (not the original course inputs), names are Ada and Grace and the initial counter is 2. It changes 2→3→4, once per name.
```python
names = ['Ada', 'Grace']  # Your two names
length = 2  # Your starting value
for name in names:
    length += 1  # Increment once per name
    print(length)  # Inside: prints 3, then 4
print(length)  # Outside: prints only the final 4
```
names[0] is Ada and names[1] is Grace: indexing begins at zero. The course supplies the loop/indexing method; the values above are our derived variation [e1]."""
    lab[2].provider.text = text
    first = run(
        lab,
        text="Explain the loop fully: Ada/Grace, initial 2, trace 2→3→4, commented code, inner/outer print and list indices.",
    )
    assert first["answer"] == text and first["model_calls"] == 1
    assert "each requested part" in SYSTEM and "missing part explicitly" in SYSTEM
    assert "complete code" in SYSTEM


def test_all_premises_recent_questions_and_failed_status_reach_last_turn(lab):
    questions = [
        "Keep initial total 7 and a two-node graph; distinguish a derived example.",
        "Now use weighted edges?",
        "Keep original assumptions; why?",
        "Focus on the queue.",
        "Explain the last line.",
        "What was my original starting value?",
    ]
    for i, q in enumerate(questions):
        result = run(lab, key=f"t{i}", text=q)
        assert result["status"] == "completed"
    data = lab[2].provider.requests[-1]
    assert [p["learner_text"] for p in data["dialogue"]] == questions[:-1]
    assert all(p["answer"] == lab[2].provider.text for p in data["dialogue"])
    assert data["learner_question"] == questions[-1]
    assert "take priority" in SYSTEM and "Previous answers may be wrong" in SYSTEM
    with pytest.raises(StudyError, match="TUTOR_SESSION_BUDGET"):
        submit(lab, key="seventh", text="Why?")
    assert len(lab[2].provider.requests) == 6


def test_paraphrased_socratic_question_publishes_without_literal_focus(lab):
    lab[2].provider.hook = lambda d: dict(
        outcome="socratic_prompt",
        text="Which indentation level runs exactly once after the loop finishes? [e1]",
    )
    result = run(lab, text="Should the final print be inside or outside?", socratic=True)
    assert result["status"] == "completed" and result["outcome"] == "socratic_prompt"


def test_long_answer_publishes_without_truncation(lab):
    text = "Step by step [e1].\n" + "for item in items:\n    count += 1\n" * 120
    lab[2].provider.text = text
    result = run(lab)
    assert len(text) > 3000 and result["status"] == "completed" and result["answer"] == text


def test_short_exact_restatement_is_not_source_only(lab):
    row = lab[1].read(lab[3], "READ")["evidence"][0]
    short = row["text"].split(" distances", 1)[0]
    assert short in row["text"]
    lab[2].provider.text = f"{short} [e1]"
    result = run(lab)
    assert result["status"] == "completed"


def test_focused_socratic_question_and_specific_followup(lab):
    lab[2].provider.hook = lambda d: dict(
        outcome="socratic_prompt",
        text="For the final print, which indentation level runs once after the loop? [e1]",
        focus="final print",
    )
    first = run(lab, text="Should the final print be inside or outside?", socratic=True)
    assert first["status"] == "completed" and "final print" in first["answer"]
    lab[2].provider.hook = None
    lab[
        2
    ].provider.text = "Your claim that the counter changes once needs checking: count the iterations first, then inspect which indentation level owns the final statement [e1]."
    assert run(lab, key="reply", text="I think it changes once.")["answer"] == lab[2].provider.text
    assert lab[2].provider.requests[-1]["dialogue"][0]["answer"] == first["answer"]


@pytest.mark.parametrize(
    "response,code",
    [
        (
            {"outcome": "answered", "text": "BFS levels give shortest path distances in edges. [e1]"},
            "TUTOR_SOURCE_ONLY",
        ),
        (
            {"outcome": "socratic_prompt", "text": "Compare with the course statement. [e1]"},
            "TUTOR_FOCUS_REQUIRED",
        ),
        ({"outcome": "answered", "text": "Explanation [foreign]"}, "TUTOR_CITATION_MISMATCH"),
        ({"outcome": "answered", "text": "Explanation without a citation"}, "TUTOR_CITATION_MISMATCH"),
        ({"outcome": "answered", "text": "X" * ANSWER_MAX_CHARS + " [e1]"}, "TUTOR_PROTOCOL_FAILURE"),
        (
            {"outcome": "insufficient_evidence", "text": "But here is an unsupported answer"},
            "TUTOR_ABSTENTION_CONTRACT",
        ),
        (
            {"outcome": "answered", "text": "Explanation [e1]", "usage": {"prompt_tokens": -1}},
            "TUTOR_PROTOCOL_FAILURE",
        ),
    ],
)
def test_invalid_reply_stops_once_preserves_draft_and_never_repairs(lab, response, code):
    lab[2].provider.hook = lambda d: response
    result = run(lab, socratic=response["outcome"] == "socratic_prompt")
    assert result["status"] == "failed" and result["error_code"] == code
    assert result["answer"] is None and not result["citations"] and result["model_calls"] == 1
    assert checkpoint(lab)["response"] == response
    lab[2].execute(dict(turn_id=result["turn_id"], session_id=lab[3]["session_id"]))
    assert len(lab[2].provider.requests) == 1


def test_evidence_absence_abstains_without_any_model_call(lab):
    lab[1].empty = True
    result = run(lab)
    assert result["status"] == "completed" and result["answer"] == ABSTENTION
    assert not result["model_calls"] and not result["reserved_tokens"] and not result["citations"]
    assert not lab[2].provider.requests


def test_partial_evidence_missing_requested_part_is_explicit_and_saved(lab):
    lab[
        2
    ].provider.text = "The course explains BFS levels as unweighted distances [e1]. It does not establish a weighted-edge algorithm; that requested part remains unsupported. Would you like to split that question?"
    result = run(lab, text="Explain unweighted distances and prove a weighted variant.")
    assert result["answer"] == lab[2].provider.text


@pytest.mark.parametrize("change", ["missing", "revision", "text"])
def test_source_invalidated_during_generation_cannot_publish(lab, change):
    original = lab[1].read

    def hook(data):
        if change == "missing":
            lab[1].missing = True
        elif change == "revision":
            lab[1].valid = False
        else:

            def changed(*a, **kw):
                result = original(*a, **kw)
                for row in result["evidence"]:
                    row["text"] = "A replaced source with the same ID"
                return result

            lab[1].read = changed
        return dict(outcome="answered", text=lab[2].provider.text, usage={"completion_tokens": 70})

    lab[2].provider.hook = hook
    submit(lab)
    lab[2].execute(lab[0].candidates()[0])
    with lab[0].connect() as conn:
        result = conn.execute("SELECT * FROM tutor_turn ORDER BY ordinal DESC LIMIT 1").fetchone()
    assert result["status"] == "failed" and result["answer"] is None
    assert result["usage"] == [{"completion_tokens": 70}]
    assert checkpoint(lab)["phase"] == "received"


def test_budget_overflow_stops_before_generation_without_trimming_context(lab):
    original = lab[1].read

    def huge(*a, **kw):
        result = original(*a, **kw)
        for row in result["evidence"]:
            row["text"] = "完整课程内容" * 25000
        return result

    lab[1].read = huge
    result = run(lab)
    assert result["error_code"] == "TUTOR_BUDGET_EXHAUSTED" and result["model_calls"] == 0
    assert not lab[2].provider.requests
    assert len(checkpoint(lab)["evidence"][0]["text"]) == 150000


def test_queued_cancel_and_late_running_response_never_publish(lab):
    submit(lab)
    command(lab, "CANCEL", client_turn_id="turn-1")
    assert not lab[0].candidates() and not lab[2].provider.requests

    def cancel(data):
        command(lab, "CANCEL", client_turn_id="t2")
        return dict(outcome="answered", text=lab[2].provider.text, usage={"completion_tokens": 70})

    lab[2].provider.hook = cancel
    result = run(lab, key="t2")
    assert result["status"] == "cancelled" and result["answer"] is None
    assert result["usage"] == [{"completion_tokens": 70}]
    assert checkpoint(lab)["response"]["text"] == lab[2].provider.text


def test_unknown_send_reservation_is_not_retried(lab):
    def unknown(data):
        raise TimeoutError("delivery unknown")

    lab[2].provider.hook = unknown
    result = run(lab)
    assert result["error_code"] == "TUTOR_UNKNOWN_MODEL_OUTCOME" and result["reserved_tokens"] > 0
    assert checkpoint(lab)["phase"] == "reserved"
    submit(lab)
    assert len(lab[2].provider.requests) == 1


@pytest.mark.parametrize("phase", ["prepared", "received", "reserved"])
def test_restart_checkpoint_sends_at_most_once(lab, phase):
    submit(lab)
    with lab[0].connect() as conn:
        session, turn = lab[0].rows(conn, lab[0].candidates()[0]["turn_id"])
        state = lab[2].prepare(session, turn, [])
        state["phase"] = phase
        if phase in {"received", "reserved"}:
            lab[2].reserve_call(conn, session, turn, state["reservation"])
        if phase == "received":
            state["response"] = dict(outcome="answered", text=lab[2].provider.text)
        lab[0].checkpoint(conn, turn["turn_id"], state)
    lab[2].execute(lab[0].candidates()[0])
    result = command(lab, "GET")["turns"][0]
    assert result["status"] == ("failed" if phase == "reserved" else "completed")
    assert len(lab[2].provider.requests) == (1 if phase == "prepared" else 0)
    assert result["model_calls"] == 1


def test_engine_owner_course_and_version_boundaries(lab):
    old = TutorStore(lab[0].dsn)
    old.initialize()  # Additive migration is idempotent for both runtimes.
    legacy = old.command(Command(**lab[3], operation="CREATE", request_key="s"))["session"]
    assert legacy["session_id"] != lab[3]["session_id"]
    assert len(command(lab, "LIST")["sessions"]) == 1
    with pytest.raises(StudyError, match="SESSION_NOT_FOUND"):
        command(lab, "GET", session_id=legacy["session_id"])
    submit(lab)
    assert not old.candidates()
    for changed in ({"owner_id": 9}, {"course_id": "foreign"}):
        with pytest.raises(StudyError, match="COURSE_UNAVAILABLE"):
            command(lab, "GET", **changed)
        with pytest.raises(StudyError, match="SESSION_NOT_FOUND"):
            lab[0].command(Command(**{**lab[3], **changed}, operation="GET"))
    lab[1].scope["revision"] = 2
    with pytest.raises(StudyError, match="SESSION_STALE"):
        command(lab, "GET", revision=2)


@pytest.fixture
def historical_review_zip():
    configured = os.environ.get("PHASE1D_FAILURE_ZIP")
    if not configured:
        pytest.skip("Private historical review archive is only available to the offline audit")
    path = Path(configured)
    assert (
        hashlib.sha256(path.read_bytes()).hexdigest()
        == "832e20a6e066603b57a858a50ddbd2eda355757ba821e4119c6056339299b30d"
    )
    return path


def test_frozen_real_failure_unchanged_and_not_relabelled(historical_review_zip):
    with zipfile.ZipFile(historical_review_zip) as archive:
        outcomes = json.loads(archive.read("outcomes.json"))
        assert [r["status"] for r in outcomes] == ["completed", "completed", "failed"]
        assert "Ada" not in outcomes[0]["answer"] and "Grace" not in outcomes[0]["answer"]
        assert "final print" not in outcomes[1]["answer"]
        assert outcomes[2]["error_code"] == "TUTOR_REPAIR_BUDGET_UNAVAILABLE"
        # All original learner premises are conveyed verbatim in the new context;
        # this demonstrates transport, not a model's ability to obey them.
        assert "Ada" not in SYSTEM and "Grace" not in SYSTEM


def test_citation_existence_does_not_prove_semantic_support(lab):
    lab[2].provider.text = "Incorrect unsupported claim: BFS solves arbitrary negative weighted paths [e1]."
    result = run(lab)
    assert result["status"] == "completed"  # Known semantic negative; NOT quality PASS.
    assert "negative weighted" in result["answer"]
    assert source_only("BFS levels give shortest path distances in edges. [e1]", result["citations"])


def test_original_real_questions_and_authored_three_turns_fit_one_request_each(historical_review_zip, lab):
    with zipfile.ZipFile(historical_review_zip) as archive:
        original = json.loads(archive.read("outcomes.json"))
        evidence = json.loads(archive.read("course-evidence.json"))["evidence"]
    ids = list(dict.fromkeys(c["evidence_id"] for row in original[:2] for c in row["citations"]))
    rows = [e for e in evidence if e["evidence_id"] in ids]
    check_authored_loop_turns(lab, original, rows)


def test_synthetic_loop_questions_and_authored_three_turns_fit_one_request_each(lab):
    prompts = [
        dict(
            learner_text="Show Ada and Grace in a for loop, starting at 2. Trace the counter, show the code and explain list indices.",
            socratic=False,
        ),
        dict(learner_text="Guide me on where the final print should go.", socratic=True),
        dict(learner_text="I count one update. What did I miss in my example?", socratic=False),
    ]
    rows = [
        dict(
            evidence_id="e1",
            text="A for loop visits each list item once. A statement inside the loop runs on each iteration; a statement after it runs once. List indices start at zero.",
            start_ms=1000,
            end_ms=2000,
            source_type="SUBTITLE",
        )
    ]
    check_authored_loop_turns(lab, prompts, rows)


def check_authored_loop_turns(lab, prompts, rows):
    original_read = lab[1].read

    def read(scope, action="CHECK", **kw):
        result = original_read(scope, action, **kw)
        if action != "CHECK":
            wanted = kw.get("evidence_ids")
            result["evidence"] = rows if wanted is None else [e for e in rows if e["evidence_id"] in wanted]
        return result

    lab[1].read = read
    eid = rows[0]["evidence_id"]
    answers = [
        f"The loop avoids repeated indexed statements. For your variation, names are Ada and Grace, initially length=2; updates are 2→3→4.\n```python\nnames = ['Ada', 'Grace']  # Learner inputs\nlength = 2  # Initial value\nfor name in names:\n    length += 1  # Once per element\n    print(length)  # Inside: 3 then 4\nprint(length)  # Outside: final 4\n```\nnames[0] is Ada, names[1] is Grace. These values are derived from your changed assumptions, not the original example [{eid}].",
        f"For the final print, which indentation level runs once after all iterations? [{eid}]",
        f"You counted only one update, but your list has two elements: starting at 2, the counter becomes 3 after Ada and 4 after Grace. The final print belongs outside for one final 4; inside would print 3 and 4. This applies the course rule to your variation [{eid}].",
    ]
    for i, item in enumerate(prompts):
        lab[2].provider.hook = lambda d, i=i: dict(
            outcome="socratic_prompt" if i == 1 else "answered",
            text=answers[i],
            focus="final print" if i == 1 else "",
        )
        result = run(lab, key=f"loop-turn-{i}", text=item["learner_text"], socratic=item["socratic"])
        assert result["status"] == "completed" and result["answer"] == answers[i]
        assert result["model_calls"] == 1 and result["reserved_tokens"] < 64000
        data = lab[2].provider.requests[-1]
        assert [h["learner_text"] for h in data["dialogue"]] == [h["learner_text"] for h in prompts[:i]]
    # These authored replies are mechanism examples, never new model outputs.
    assert len(lab[2].provider.requests) == 3


def test_reserved_restart_failure_keeps_unpublished_learner_context(lab):
    lab[2].provider.hook = lambda d: (_ for _ in ()).throw(TimeoutError())
    assert run(lab, text="Keep my changed input: a four-vertex graph.")["status"] == "failed"
    lab[2].provider.hook = None
    assert run(lab, key="followup", text="Which input did I change?")["status"] == "completed"
    previous = lab[2].provider.requests[-1]["dialogue"][0]
    assert previous["status"] == "failed" and previous["answer"] is None
    assert "four-vertex" in previous["learner_text"]


def test_deadline_and_shutdown_before_publication_do_not_retry(lab):
    def expired(data):
        with lab[0].connect() as conn:
            conn.execute("UPDATE tutor_turn SET deadline=now()-interval '1 second'")
        return dict(outcome="answered", text=lab[2].provider.text)

    lab[2].provider.hook = expired
    result = run(lab)
    assert result["error_code"] == "TUTOR_DEADLINE" and result["model_calls"] == 1
    assert checkpoint(lab)["phase"] == "received"


def test_tombstone_during_generation_prevents_publish_and_purge_removes_history(lab):
    def deleted(data):
        with lab[0].connect() as conn:
            conn.execute("CREATE TABLE evidence_index(owner_id bigint,course_id text,state text)")
            conn.execute(
                "INSERT INTO evidence_index VALUES(%s,%s,'DELETED')",
                (lab[3]["owner_id"], lab[3]["course_id"]),
            )
        return dict(outcome="answered", text=lab[2].provider.text)

    lab[2].provider.hook = deleted
    submit(lab)
    lab[2].execute(lab[0].candidates()[0])
    with lab[0].connect() as conn:
        row = conn.execute("SELECT * FROM tutor_turn").fetchone()
        assert row["status"] == "failed" and row["answer"] is None
    lab[0].purge_deleted()
    with lab[0].connect() as conn:
        assert conn.execute("SELECT count(*) n FROM tutor_turn").fetchone()["n"] == 0


def test_light_product_factory_rejects_real_mode_before_base_startup(monkeypatch):
    from fastapi.testclient import TestClient

    from lecturelens_real_eval.tutor.app import create_app

    monkeypatch.setenv("TUTOR_ENABLED", "true")
    monkeypatch.setenv("TUTOR_ENGINE", "light")
    monkeypatch.setenv("AGENT_LLM_MODE", "real")
    with pytest.raises(RuntimeError, match="TUTOR_MOCK_ONLY"), TestClient(create_app()):
        raise AssertionError("Real-mode factory must never enter lifespan")


def test_legacy_request_key_cannot_alias_light_session_identity(lab):
    old = TutorStore(lab[0].dsn)
    legacy = old.command(Command(**lab[3], operation="CREATE", request_key="s:light"))["session"]
    assert legacy["engine"] == "p8"
    assert legacy["session_id"] != lab[3]["session_id"]
