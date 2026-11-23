import json
import os
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from lecturelens_real_eval.tutor.app import create_app
from lecturelens_real_eval.tutor.light import SYSTEM, LightTutorRuntime
from lecturelens_real_eval.tutor.light_retrieval import QUERY_CHARS, targeted_queries
from lecturelens_real_eval.tutor.query_language import QueryLanguage, configured_query_language


@pytest.mark.parametrize("mode", ["english", "bilingual"])
def test_translation_preserves_literals_and_original_planner(monkeypatch, mode):
    question = "为什么 Ada Lovelace 的 TCP 代码调用 `parse(x[0])`？如何判断 10.5 ms 时 μ < 103.5？"
    queries = targeted_queries(question)
    assert len(queries) == 3
    language = QueryLanguage(mode, "", "")
    seen = []

    def translate(planned):
        seen.extend(planned)
        return ["What causes the call and how do I check the threshold?", "Why call it?", "How to check it?"]

    monkeypatch.setattr(language, "translate", translate)
    searches = []
    scope = {"owner_id": 1, "course_id": "lecture", "revision": 8}

    class Authority:
        def read(self, request_scope, action, **kwargs):
            assert request_scope == scope
            if action == "TUTOR_SEARCH":
                searches.append(kwargs)
            else:
                assert action == "READ" and kwargs["evidence_ids"] == ["e"]
            return {"evidence": [{"evidence_id": "e", "text": "An excerpt."}]}

    runtime = LightTutorRuntime(SimpleNamespace(engine="light"), Authority(), query_language=language)
    state = runtime.prepare(scope, {"learner_text": question, "socratic": True}, [])
    data = json.loads(state["messages"][-1]["content"])
    assert state["messages"][0]["content"] == SYSTEM
    assert data["learner_question"] == question and data["socratic"]
    assert len(data["current_evidence"]) == 1 and seen == queries
    assert [row["tutor_strategy"] for row in searches] == ["HYBRID_16"] * 3
    wire = [row["query"] for row in searches]
    english = [query.split("\n", 1)[-1] for query in wire]
    assert all(
        term in english[0] for term in ("Ada Lovelace", "TCP", "`parse(x[0])`", "10.5 ms", "μ < 103.5")
    )
    if mode == "bilingual":
        assert [query.split("\n", 1)[0] for query in wire] == queries


def test_english_question_bypasses_translation_even_with_chinese_history(monkeypatch):
    language = QueryLanguage("english", "", "")
    monkeypatch.setattr(language, "translate", lambda _: pytest.fail("English turn must bypass translation"))
    original = ["Continue from the formula.", "此前的中文问题"]
    assert language.rewrite(original[0], original) == original


@pytest.mark.parametrize("response", [None, [], ["ends", "中文"], ["ends", ""], ["ends", "😀" * QUERY_CHARS]])
def test_failed_or_overflowing_part_falls_back_atomically(monkeypatch, response):
    language = QueryLanguage("english", "", "")
    monkeypatch.setattr(language, "translate", lambda _: response)
    original = ["为什么出现这个边界？", "如何应用该公式？"]
    assert language.rewrite(original[0], original) == original


def test_missing_dependency_uses_original(monkeypatch, tmp_path):
    monkeypatch.setenv("TUTOR_QUERY_LANGUAGE", "english")
    monkeypatch.setenv("TUTOR_TRANSLATION_PYTHON", str(tmp_path / "absent-python"))
    monkeypatch.setenv("TUTOR_TRANSLATION_MODEL_DIR", str(tmp_path))
    original = ["公式是什么？"]
    assert configured_query_language().rewrite(original[0], original) == original


def test_worker_rejects_unavailable_or_corrupt_weights(tmp_path):
    (tmp_path / "sentencepiece.model").write_bytes(b"unverified")
    language = QueryLanguage("english", sys.executable, tmp_path)
    original = ["这个代码是什么意思？"]
    assert language.rewrite(original[0], original) == original


def test_slow_dependency_is_killed_and_original_query_is_used(monkeypatch, tmp_path):
    from lecturelens_real_eval.tutor import query_language

    executable = tmp_path / "slow-python"
    executable.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(30)\n")
    executable.chmod(0o700)
    monkeypatch.setattr(query_language, "TRANSLATION_TIMEOUT_SECONDS", 0.1)
    original = ["如何使用 Ada 的方法？"]
    assert QueryLanguage("bilingual", executable, tmp_path).rewrite(original[0], original) == original


def test_normal_light_app_enables_opt_in_and_defaults_to_original(monkeypatch):
    for name, value in {
        "TUTOR_ENABLED": "true",
        "TUTOR_ENGINE": "light",
        "TUTOR_PROVIDER": "mock",
        "AGENT_LLM_MODE": "mock",
        "AGENT_DATABASE_URL": os.environ["AGENT_TEST_DATABASE_URL"],
        "AGENT_JAVA_BASE_URL": "http://127.0.0.1:1",
        "STUDY_AGENT_ENABLED": "false",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("TUTOR_QUERY_LANGUAGE", raising=False)
    with TestClient(create_app(retriever=object(), secret="s" * 32)) as client:
        assert client.app.state.tutor.query_language is None
    monkeypatch.setenv("TUTOR_QUERY_LANGUAGE", "english")
    with TestClient(create_app(retriever=object(), secret="s" * 32)) as client:
        assert client.app.state.tutor.query_language.mode == "english"
