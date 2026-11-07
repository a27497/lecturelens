"""Fixed public-development answers and PG protocol checks, never real-model quality."""

import ast
import copy
import hashlib
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import psycopg
import pytest
from lecturelens_real_eval.runner import SnapshotAuthority
from lecturelens_real_eval.tutor.citations import assembled_citation_ids, inline_citation_ids
from lecturelens_real_eval.tutor.contracts import ABSTENTION, Command
from lecturelens_real_eval.tutor.python_runtime import FINISH_LIMITS, SYSTEM, PythonTutorRuntime
from lecturelens_real_eval.tutor.runtime import SYSTEM as V9_SYSTEM
from lecturelens_real_eval.tutor.runtime import TutorRuntime as V9TutorRuntime
from lecturelens_real_eval.tutor.store import TutorStore
from lecturelens_real_eval.tutor_channel import EvalError
from lecturelens_real_eval.tutor_runner import TutorProvider, citation_ids, verify_inputs
from psycopg import sql
from psycopg.conninfo import make_conninfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(1, str(ROOT / "eval/tutor-python-contract-v1"))
import contract_check as contract  # noqa: E402
from public_bridge import summarize  # noqa: E402
from public_dataset import read, select  # noqa: E402
from shared import validate_citations  # noqa: E402

FIXTURE = read(Path(__file__).parent / "fixtures/tutor_python_contract.json")


def render(key, lecture):
    case = FIXTURE["cases"][key]
    parts, ids, claims = [], [], []
    for n, segment in enumerate(case["segments"], 1):
        evidence = [
            next(e for e in lecture["evidence"] if e["line_start"] <= line <= e["line_end"])
            for line in segment["source_lines"]
        ]
        chosen = list(dict.fromkeys(e["evidence_id"] for e in evidence))
        parts.append(segment["text"] + " " + " ".join(f"[{eid}]" for eid in chosen))
        ids.extend(chosen)
        claims.append(
            dict(claim_id=f"claim-{n}", text=segment["text"], requires_citation=True, citation_ids=chosen)
        )
    return " ".join(parts) or ABSTENTION, list(dict.fromkeys(ids)), claims


def test_prompt_and_request_bytes_preserve_parent_and_limits():
    assert "use parentheses for math/indexing" in V9_SYSTEM
    assert "use parentheses for math/indexing" not in SYSTEM
    assert "Never rewrite indexing as a function call" in SYSTEM
    assert all(
        x in SYSTEM
        for x in ("data[row_index, column_index]", "matrix[:, start:stop]", "inline code", "fenced code")
    )
    for key in FIXTURE["target_turns"]:
        assert all(code not in SYSTEM for code in FIXTURE["cases"][key]["code_snippets"])
    assert all(
        x in SYSTEM for x in ("4 distinct evidence ids", "500 characters", "1600 characters", ABSTENTION)
    )
    assert "code formatting never bypasses" in SYSTEM and "even inside code" in SYSTEM
    session, turn = {"summary": ""}, {"learner_text": "slice this array", "socratic": False}
    for state in (
        {"selected": [], "observations": []},
        {"selected": [], "observations": [{"tool": "search_tutor_evidence"}]},
        {
            "selected": [],
            "observations": [{"tool": "finish_tutor_turn", "error": "TUTOR_FINISH_REPAIR_REQUIRED"}],
        },
    ):
        runtime = PythonTutorRuntime(None, None)
        old = V9TutorRuntime(None, None)
        with (
            patch.object(runtime, "read_evidence", return_value=[]),
            patch.object(old, "read_evidence", return_value=[]),
        ):
            messages, schemas, amount = runtime.request(session, turn, state, [])
            old_messages, old_schemas, _ = old.request(session, turn, state, [])
        assert messages[0]["content"] == SYSTEM and messages[1:] == old_messages[1:]
        assert amount == len(json.dumps([messages, schemas], ensure_ascii=False).encode()) + 1200
        assert amount > len(json.dumps([old_messages, old_schemas], ensure_ascii=False).encode()) + 1200
        for new_schema, old_schema in zip(schemas, old_schemas, strict=True):
            if new_schema["function"]["name"] == "finish_tutor_turn":
                assert new_schema["function"]["description"] == FINISH_LIMITS
                assert new_schema["function"]["parameters"] == old_schema["function"]["parameters"]
            else:
                assert new_schema == old_schema


@pytest.mark.parametrize(
    "code",
    [
        "data[29, 19]",
        "data[0:4, 0:10]",
        "data[:3, -4:]",
        "A[:, :1]",
        "data[row_index]",
        "matrix[indices[0]]",
        "values[-1]",
        "mapping['e1']",
        "[0, 2, -2]",
    ],
)
@pytest.mark.parametrize("wrapper", ["{}", "`{}`", "```python\n{}\n```"])
def test_non_id_code_is_unchanged_and_not_a_citation(code, wrapper):
    ast.parse(code)
    text = wrapper.format(code)
    assert inline_citation_ids(text) == []
    assert assembled_citation_ids(text + " [e2] [e1]", "[e1] [e3]") == ["e2", "e1", "e3"]


@pytest.mark.parametrize("text", ["data[e999]", "`[e999]`", "```python\n# [e999]\n```", "[" + "0" * 64 + "]"])
def test_code_markup_never_hides_foreign_id_shaped_candidates(text):
    authority = type("A", (), {"rows": lambda self, scope: [{"evidence_id": "e1"}]})()
    blocked = []
    channel = type("C", (), {"ledger": type("L", (), {"block": lambda self, code: blocked.append(code)})()})()
    provider = TutorProvider(channel, authority)
    with pytest.raises(EvalError, match="CITATION_FABRICATED"):
        provider.validate(
            dict(
                name="finish_tutor_turn", arguments=dict(outcome="answered", text=text, evaluation="E" * 501)
            )
        )
    assert blocked == ["REAL_EVAL_CITATION_FABRICATED"]
    assert citation_ids(dict(text=text)) == inline_citation_ids(text)


def test_historical_chain_and_new_development_identity_are_distinct():
    verify_inputs()
    identity = contract.verify_candidate()
    assert identity != contract.PARENT_SHA
    assert (
        hashlib.sha256((ROOT / "eval/p8-tutor/frozen.json").read_bytes()).hexdigest() == contract.PARENT_SHA
    )
    assert contract.read(contract.HERE / "candidate.json")["runtime_entrypoint"] == contract.ENTRYPOINT


def test_new_identity_detects_source_drift_without_relabeling_parent(tmp_path, monkeypatch):
    manifest = read(contract.HERE / "candidate.json")
    for name in [*manifest["files"], "eval/p8-tutor/frozen.json"]:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    module = tmp_path / "agent-service/src/lecturelens_real_eval/tutor/python_runtime.py"
    module.write_text(module.read_text() + "\n# changed development prompt\n")
    verify_inputs()  # Historical verification still succeeds on the unchanged parent.
    monkeypatch.setattr(contract, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="CONTRACT_INPUT_CHANGED"):
        contract.verify_candidate()


def test_frozen_scope_is_complete_development_only_and_hash_bound(tmp_path):
    plan_path = contract.HERE / "development-pilot-v1.json"
    plan, scripts, snapshot = contract.load_plan(plan_path)
    assert [d["dialogue_id"] for d in scripts] == ["python-01", "sheets-01"]
    assert [len(d["turns"]) for d in scripts] == [4, 4]
    assert set(snapshot["lectures"]) == {"carpentries-python", "carpentries-spreadsheets"}
    assert plan["execution_authorized"] is False
    broken = tmp_path / "changed.json"
    broken.write_text(json.dumps({**plan, "turn_keys": plan["turn_keys"][:-1]}))
    with pytest.raises(ValueError, match="MANIFEST_HASH_MISMATCH"):
        contract.load_plan(broken)
    (
        full_snapshot,
        groups,
    ) = select("development")
    for field, value in (("dialogue_id", "sql-01"), ("turns", 3), ("turns_sha256", "0" * 64)):
        changed = copy.deepcopy(plan)
        changed["sessions"][0][field] = value
        with pytest.raises(ValueError):
            contract.validate_plan(changed, full_snapshot, groups, contract.verify_candidate())


class FixedAuthority(SnapshotAuthority):
    """Controlled observations isolate publication; they are not a retrieval-quality oracle."""

    ids = ()

    def read(self, scope, action="CHECK", **args):
        if action == "SEARCH":
            return super().read(scope, "READ", evidence_ids=list(self.ids))
        return super().read(scope, action, **args)


class FixedProvider:
    """No network transport or reviewer; hand-constructed search/finish decisions."""

    def __init__(self):
        self.answer, self.outcome, self.messages = None, None, []

    def decide(self, messages, schemas, timeout):
        assert messages[0]["content"] == SYSTEM
        self.messages.append(messages)
        body = json.loads(messages[-1]["content"])
        if not body["observations"]:
            return dict(name="search_tutor_evidence", arguments={"query": body["learner_text"][:500]})
        return dict(name="finish_tutor_turn", arguments=dict(outcome=self.outcome, text=self.answer))


@pytest.fixture
def lab():
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    schema = "python_contract_" + uuid.uuid4().hex
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    store = TutorStore(make_conninfo(dsn, options=f"-csearch_path={schema},public"))
    snapshot, scripts = select("development")
    authority, provider = FixedAuthority(snapshot), FixedProvider()
    runtime = PythonTutorRuntime(store, authority, provider)
    runtime.initialize()
    yield store, authority, provider, runtime, snapshot, scripts
    runtime.close()
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.mark.parametrize("did", FIXTURE["sessions"])
def test_fixed_answers_publish_original_code_and_score_only_as_fixtures(lab, did, tmp_path):
    store, authority, provider, runtime, snapshot, scripts = lab
    script = next(d for d in scripts if d["dialogue_id"] == did)
    scope = dict(owner_id=811010, course_id="contract-" + uuid.uuid4().hex, revision=1)
    authority.register(scope, script["lecture_id"])
    session = runtime.command(Command(**scope, operation="CREATE", request_key="session"))["session"]
    scope["session_id"] = session["session_id"]
    rows, labels = [], {}
    lecture = snapshot["lectures"][script["lecture_id"]]
    evidence = {e["evidence_id"]: e for e in lecture["evidence"]}
    for n, task in enumerate(script["turns"], 1):
        key = f"{did}:{n}"
        if key not in FIXTURE["cases"]:
            break
        case = FIXTURE["cases"][key]
        answer, ids, claims = render(key, lecture)
        assert len(ids) <= 4 and set(ids) <= evidence.keys()
        assert bool(case["segments"]) != task["expected_insufficient"]
        for code in case["code_snippets"]:
            parsed = ast.parse(code)
            assert code in answer or code == "data[:3, -4:]"
            if key in FIXTURE["target_turns"]:
                assert any(isinstance(node, ast.Subscript) for node in ast.walk(parsed))
        authority.ids = ids
        provider.answer, provider.outcome = answer, case["expected_outcome"]
        runtime.command(Command(**scope, operation="TURN", client_turn_id=f"turn-{n}", text=task["text"]))
        runtime.execute(next(c for c in store.candidates() if c["session_id"] == scope["session_id"]))
        turn = runtime.command(Command(**scope, operation="GET"))["turns"][-1]
        assert turn["status"] == "completed" and turn["answer"] == answer
        assert turn["model_calls"] == 2 and turn["outcome"] == case["expected_outcome"]
        assert [e["evidence_id"] for e in turn["citations"]] == ids
        assert json.loads(provider.messages[-1][-1]["content"])["learner_text"] == task["text"]
        assert len(json.loads(provider.messages[-1][-1]["content"])["history"]) == n - 1
        turn.update(
            turn_key=key,
            script=task,
            course_id=script["course_id"],
            dialogue_id=did,
            citations=[evidence[eid] for eid in ids],
            review=None,
        )
        checks = [
            dict(claim_id=c["claim_id"], evidence_id=eid, label="supported", quote=evidence[eid]["text"])
            for c in claims
            for eid in c["citation_ids"]
        ]
        label = dict(
            complete=True,
            overall_supported="supported",
            reason="HAND_CONSTRUCTED_CONTRACT_FIXTURE",
            task_correct=True,
            context_consistent=True,
            abstention_correct=True,
            claims=claims,
            citation_checks=checks,
        )
        validate_citations(label, turn)
        rows.append(turn)
        labels[key] = label
    result = summarize(dict(rows=rows, config={"data_kind": "MOCK"}), labels)
    assert result["quality_status"] == "MOCK_NOT_QUALITY"
    assert result["model_human_support_agreement"]["comparable"] == 0
    assert result["task_correctness"]["assessed"] == len(rows)
    assert store.command(Command(**scope, operation="GET"))["session"]["model_calls"] == 2 * len(rows)
    (tmp_path / f"{did}-fixed-contract.json").write_text(
        json.dumps(
            dict(
                data_kind="HAND_CONSTRUCTED_CODEX_MOCK_NOT_QUALITY",
                rows=rows,
                requests=provider.messages,
                fixture_labels=labels,
                summary=result,
            ),
            indent=2,
            default=str,
        )
        + "\n"
    )


@pytest.mark.parametrize(
    "suffix",
    ["[e999]", "`[e999]`", "```python\n# [e999]\n```", "[v2-quantum-l2-p04-e00]", "[" + "0" * 64 + "]"],
)
def test_foreign_candidates_fail_even_when_code_and_valid_citations_coexist(lab, suffix):
    store, authority, provider, runtime, snapshot, _ = lab
    scope = dict(owner_id=811010, course_id="rejected-" + uuid.uuid4().hex, revision=1)
    authority.register(scope, "carpentries-python")
    session = runtime.command(Command(**scope, operation="CREATE", request_key="s"))["session"]
    scope["session_id"] = session["session_id"]
    answer, ids, _ = render("python-01:3", snapshot["lectures"]["carpentries-python"])
    authority.ids, provider.answer, provider.outcome = ids, answer + " " + suffix, "answered"
    runtime.command(
        Command(**scope, operation="TURN", client_turn_id="bad", text="Show valid Python indexing")
    )
    runtime.execute(store.candidates()[0])
    turn = runtime.command(Command(**scope, operation="GET"))["turns"][-1]
    assert turn["status"] == "failed" and turn["error_code"] == "TUTOR_CITATION_MISMATCH"
    assert turn["answer"] is None


@pytest.mark.parametrize("text", ["`data[29, 19]`", "data[:3, 36:] [e1", "data[0:4, 0:10] [fake-id]"])
def test_code_or_malformed_markers_cannot_substitute_for_a_required_citation(lab, text):
    store, authority, provider, runtime, snapshot, _ = lab
    scope = dict(owner_id=811010, course_id="uncited-" + uuid.uuid4().hex, revision=1)
    authority.register(scope, "carpentries-python")
    session = runtime.command(Command(**scope, operation="CREATE", request_key="s"))["session"]
    scope["session_id"] = session["session_id"]
    _, ids, _ = render("python-01:3", snapshot["lectures"]["carpentries-python"])
    authority.ids, provider.answer, provider.outcome = ids, text, "answered"
    runtime.command(Command(**scope, operation="TURN", client_turn_id="uncited", text="Use a slice"))
    runtime.execute(store.candidates()[0])
    turn = runtime.command(Command(**scope, operation="GET"))["turns"][-1]
    assert turn["status"] == "failed" and turn["error_code"] == "TUTOR_CITATION_MISMATCH"
    assert turn["answer"] is None
