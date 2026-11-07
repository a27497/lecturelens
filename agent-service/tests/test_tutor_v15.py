"""V15 product mechanisms on a disposable PG schema; never provider quality."""

import copy
import hashlib
import json
import os
import uuid
from pathlib import Path

import httpx
import psycopg
import pytest
from lecturelens_real_eval.tutor.bounded_runtime import (
    HEADER,
    BlockFinish,
    BoundedTutorRuntime,
    render,
)
from lecturelens_real_eval.tutor.claim_grounding_runtime import LessonAuthority
from lecturelens_real_eval.tutor.contracts import Command
from lecturelens_real_eval.tutor.store import TutorStore
from psycopg import sql
from psycopg.conninfo import make_conninfo

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    assert os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") == "1"
    original = os.environ.get

    def get(key, *args):
        if key in {"AGENT_LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"}:
            pytest.fail("No credential access in phase checks")
        return original(key, *args)

    monkeypatch.setattr(os.environ, "get", get)
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kw: pytest.fail("No real provider transport"))


@pytest.fixture
def lab():
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    schema = "v15_" + uuid.uuid4().hex
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    store = TutorStore(make_conninfo(dsn, options=f"-csearch_path={schema},public"))
    snapshot = json.loads((ROOT / "eval/tutor-v14-fresh-v1/snapshot.json").read_text())
    authority = LessonAuthority(snapshot)
    scope = dict(owner_id=811012, course_id="v15-" + uuid.uuid4().hex, revision=1)
    authority.register(scope, "carpentries-python")
    runtime = BoundedTutorRuntime(store, authority)
    runtime.initialize()
    scope["session_id"] = runtime.command(Command(**scope, operation="CREATE", request_key="s"))["session"][
        "session_id"
    ]
    try:
        yield store, authority, runtime, scope
    finally:
        runtime.close()
        with psycopg.connect(dsn) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def run(lab, provider, key="t1", text="Explain loops", **kwargs):
    store, _, runtime, scope = lab
    runtime.provider = provider
    runtime.command(Command(**scope, operation="TURN", client_turn_id=key, text=text, **kwargs))
    runtime.execute(store.candidates()[0])
    return runtime.command(Command(**scope, operation="GET"))["turns"][-1]


class Provider:
    def __init__(self, finish):
        self.finish, self.requests = finish, []

    def decide(self, messages, schemas, timeout):
        self.requests.append(copy.deepcopy((messages, schemas)))
        body = json.loads(messages[-1]["content"])
        if not body["observations"]:
            return dict(
                name="search_tutor_evidence",
                arguments=dict(query="loop"),
                usage=dict(prompt_tokens=100, completion_tokens=20),
            )
        return dict(
            name="finish_tutor_turn",
            arguments=self.finish(body),
            usage=dict(prompt_tokens=100, completion_tokens=40),
        )


def block(body, text="A course statement", **kwargs):
    e = body["evidence"][0]
    return dict(text=text, evidence_id=e["evidence_id"], quote=e["text"][:80], basis="course", **kwargs)


def test_delivery_v2_contract_keeps_every_requirement_and_threshold():
    base = json.loads((ROOT / "eval/tutor-v14-fresh-v1/questions.json").read_text())
    new = json.loads((ROOT / "eval/tutor-repair-phase-v1/contract-v2.json").read_text())
    old_tasks = {f"{d['dialogue_id']}:{i}": t for d in base["dialogues"] for i, t in enumerate(d["turns"], 1)}
    assert set(old_tasks) == set(new["tasks"])
    for key, old in old_tasks.items():
        task = new["tasks"][key]
        assert task["reference_points"] == old["reference_points"]
        assert task["original_text"] == old["text"]
        assert len(task["obligations"]) == len(old["reference_points"])
    assert new["tasks"]["v14-sheets-lineends:2"]["text"].endswith(
        "Include the unit's Excel reopening/parsing counterexample when assessing the universal-failure claim."
    )
    assert (
        new["thresholds"]
        == json.loads((ROOT / "eval/tutor-v14-fresh-v1/grading-rules.json").read_text())["requirements"]
    )
    assert len(new["revisions"]) == 1


@pytest.mark.parametrize("char", ["a", "中", "😀", "\n"])
def test_delivery_every_schema_valid_maximum_renders_within_original_limits(char):
    answer = [
        dict(text=char * 300, evidence_id=str(i) * 64, quote="anchor", basis="derivation") for i in range(4)
    ]
    evaluation = [
        dict(text=char * 160, evidence_id=str(i) * 64, quote="anchor", basis="derivation") for i in range(2)
    ]
    proposal = BlockFinish.model_validate(
        dict(outcome="answered", blocks=answer, evaluation_blocks=evaluation)
    )
    assert len(render([b.model_dump() for b in proposal.blocks])) <= 1600
    assert len(render([b.model_dump() for b in proposal.evaluation_blocks])) <= 500
    assert render(answer).count("[") == 4


def test_delivery_canonical_render_publication_and_restart(lab):
    p = Provider(lambda b: dict(outcome="answered", blocks=[block(b)]))
    result = run(lab, p)
    assert result["status"] == "completed" and result["answer"].startswith(HEADER)
    assert len(result["citations"]) == 1 and result["citations"][0]["evidence_id"] in result["answer"]
    store, authority, _, scope = lab
    restarted = BoundedTutorRuntime(TutorStore(store.dsn), authority)
    assert restarted.command(Command(**scope, operation="GET"))["turns"][-1] == result
    assert len(p.requests) == 2


@pytest.mark.parametrize("repeat", [False, True])
def test_delivery_one_format_repair_preserves_structured_draft(lab, repeat):
    def finish(body):
        repairing = "rejected_blocks" in body
        return dict(outcome="answered", blocks=[block(body, "x" * (301 if repeat or not repairing else 300))])

    p = Provider(finish)
    result = run(lab, p)
    assert len(p.requests) == 3
    body = json.loads(p.requests[-1][0][-1]["content"])
    assert len(body["rejected_blocks"]["blocks"][0]["text"]) == 301
    assert result["status"] == ("failed" if repeat else "completed")
    if repeat:
        assert result["error_code"] == "TUTOR_FINISH_FORMAT_INVALID" and result["answer"] is None


def test_delivery_foreign_binding_never_gets_format_repair(lab):
    def finish(body):
        value = block(body, "x" * 301)
        value["evidence_id"] = "f" * 64
        return dict(outcome="answered", blocks=[value])

    p = Provider(finish)
    result = run(lab, p)
    assert result["status"] == "failed" and result["error_code"] == "TUTOR_CITATION_MISMATCH"
    assert len(p.requests) == 2 and not result["citations"]


@pytest.mark.parametrize("damage", [None, "legacy", "hash", "owner", "truncated", "capacity"])
def test_evidence_negotiation_hash_scope_and_capacity(damage):
    from lecturelens_agent.study.authority import signature
    from lecturelens_agent.study.store import StudyError
    from lecturelens_real_eval.tutor.complete_authority import CompleteEvidenceAuthority

    secret = "synthetic-test-service-secret-minimum-32"
    scope = dict(owner_id=811012, course_id="complete", revision=1)
    text = "for value in names:\n    length += 1\nprint(length)" + "x" * 1250

    def send(request):
        assert request.headers["X-LectureLens-Signature"] == signature(
            secret, request.headers["X-LectureLens-Timestamp"], request.content, request.url.path
        )
        payload = json.loads(request.content)
        assert payload["text_policy"] == "complete-v1"
        source = dict(
            evidence_id="e1",
            text=text,
            start_ms=0,
            end_ms=1,
            source_type="SUBTITLE",
            text_complete=True,
            content_hash=hashlib.sha256(text.encode()).hexdigest(),
        )
        result = {**scope, "text_policy": "complete-v1", "evidence": [source]}
        if damage == "legacy":
            del result["text_policy"]
        if damage == "owner":
            result["owner_id"] = 1
        if damage == "hash":
            source["content_hash"] = "f" * 64
        if damage == "truncated":
            source["text_complete"] = False
        if damage == "capacity":
            source["text"] = "x" * 8001
        return httpx.Response(200, json=dict(data=result))

    authority = CompleteEvidenceAuthority(
        "http://127.0.0.1:39991", secret, transport=httpx.MockTransport(send)
    )
    if damage:
        with pytest.raises(StudyError):
            authority.read(scope, "READ", evidence_ids=["e1"])
    else:
        assert authority.read(scope, "READ", evidence_ids=["e1"])["evidence"][0]["text"] == text


def test_evidence_default_candidate_mock_preserves_actual_index_syntax(lab):
    from lecturelens_real_eval.tutor.bounded_mock import SourcePreservingMock

    store, authority, runtime, scope = lab
    source = authority.snapshot["lectures"]["carpentries-python"]["evidence"][0]
    source["text"] = "The first value is values[0]; retain names=['a', 'b']."
    runtime.read_evidence(scope, [source["evidence_id"]])
    result = run(lab, SourcePreservingMock(), text="values names first")
    assert result["status"] == "completed"
    assert "values[0]" in result["answer"] and "names=['a', 'b']" in result["answer"]
    assert result["citations"][0]["text"] == source["text"]
