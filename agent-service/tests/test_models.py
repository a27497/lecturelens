import json
import os
import time
import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.postgres import PostgresSaver
from test_study import Authority

from lecturelens_agent.app import create_app
from lecturelens_agent.app import signature as retrieval_signature
from lecturelens_agent.study.authority import signature
from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.models import ModelCommand, ModelRegistry, RegistryProvider
from lecturelens_agent.study.provider import MockProvider
from lecturelens_agent.study.runtime import StudyRuntime
from lecturelens_agent.study.store import StudyError, StudyStore

SECRET = "model-management-test-secret-with-32-bytes"


@pytest.fixture
def registry(monkeypatch):
    dsn = os.environ.get("AGENT_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Real PostgreSQL required")
    for key in [
        "AGENT_LLM_BASE_URL",
        "AGENT_LLM_MODEL",
        "AGENT_LLM_API_KEY",
        "AGENT_MODEL_ENCRYPTION_KEY",
        "AGENT_MODEL_ALLOWED_ORIGINS",
        "STUDY_AGENT_ENABLED",
    ]:
        monkeypatch.delenv(key, raising=False)
    reg = ModelRegistry(dsn, SECRET)
    reg.initialize()
    reg.store.initialize()
    owner = uuid.uuid4().int % 1_000_000_000 + 1000
    yield reg, owner
    with reg.store.connect() as conn:
        sessions = conn.execute("SELECT session_id FROM study_session WHERE owner_id=%s", (owner,)).fetchall()
    with PostgresSaver.from_conn_string(dsn) as saver:
        for session in sessions:
            saver.delete_thread(session["session_id"])
    with reg.store.connect() as conn:
        conn.execute(
            "DELETE FROM study_run WHERE session_id IN (SELECT session_id FROM study_session WHERE owner_id=%s)",
            (owner,),
        )
        conn.execute("DELETE FROM study_session WHERE owner_id=%s", (owner,))
        conn.execute("DELETE FROM agent_model_routing WHERE owner_id=%s", (owner,))
        conn.execute("DELETE FROM agent_model_connection WHERE owner_id=%s", (owner,))


def command(registry, operation, **kwargs):
    reg, owner = registry
    return reg.command(ModelCommand(owner_id=owner, operation=operation, **kwargs))


def save(registry, **kwargs):
    data = {
        "name": "My local model",
        "base_url": "http://127.0.0.1:8091/v1",
        "api_key": "private-provider-key",
        "model_ids": ["generator", "critic"],
    }
    data.update(kwargs.pop("connection", {}))
    return command(registry, "SAVE", connection=data, **kwargs)


def route(registry, connection_id):
    return command(
        registry,
        "ROUTE",
        bindings={
            role: {"connection_id": connection_id, "model": model}
            for role, model in [("decision", "generator"), ("review", "critic")]
        },
    )


def test_credentials_encrypted_and_never_echoed(registry):
    saved = save(registry)
    public = command(registry, "LIST")
    assert public["connections"][0]["has_key"] is True
    assert "private-provider-key" not in json.dumps(public)
    assert "credential" not in json.dumps(public)
    reg, owner = registry
    with reg.store.connect() as conn:
        row = reg.connection(conn, owner, saved["connection_id"])
    assert "private-provider-key" not in row["credential"]
    assert reg.unseal(row["credential"]) == "private-provider-key"
    save(registry, **saved, connection={"api_key": None})
    assert command(registry, "LIST")["connections"][0]["has_key"] is True
    saved["version"] = 2
    save(registry, **saved, connection={"api_key": None, "clear_key": True})
    assert command(registry, "LIST")["connections"][0]["has_key"] is False


def test_catalog_presets_can_be_saved_without_network_but_do_not_claim_verified_models(registry):
    catalog = command(registry, "LIST")
    assert catalog["presets_checked_at"]
    assert len({preset["id"] for preset in catalog["presets"]}) == len(catalog["presets"])
    for preset in catalog["presets"]:
        assert preset["docs_url"].startswith("https://")
        saved = save(
            registry,
            connection={
                "name": preset["name"],
                "base_url": preset["base_url"],
                "model_ids": preset["models"],
            },
        )
        connection = command(registry, "LIST")["connections"][0]
        assert connection["checks"] == {}
        assert connection["model_ids"] == preset["models"]
        command(registry, "DELETE", **saved)
    assert command(registry, "LIST")["connections"] == []


@pytest.mark.parametrize(
    "url",
    [
        "https://dashscope.aliyuncs.com.attacker.example/compatible-mode/v1",
        "https://dashscope.aliyuncs.com:444/compatible-mode/v1",
        "http://dashscope.aliyuncs.com/compatible-mode/v1",
        "https://unapproved-workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    ],
)
def test_preset_trust_is_exact_origin_not_domain_wildcard(registry, url):
    with pytest.raises(StudyError, match="MODEL_ORIGIN_NOT_ALLOWED"):
        save(registry, connection={"base_url": url})


@pytest.mark.parametrize("operation", ["SAVE", "DELETE", "DISCOVER", "PROBE", "ROUTE"])
def test_connections_and_bindings_are_owner_scoped(registry, operation):
    saved = save(registry)
    reg, owner = registry
    other = (reg, owner + 1)
    with pytest.raises(StudyError, match="MODEL_CONNECTION_NOT_FOUND"):
        if operation == "SAVE":
            save(other, **saved)
        elif operation == "ROUTE":
            route(other, saved["connection_id"])
        else:
            command(other, operation, **saved, model="generator")
    assert command(other, "LIST")["connections"] == []


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest",
        "http://127.0.0.1:8080/internal",
        "https://unapproved.example/v1",
        "https://api.deepseek.com@127.0.0.1/v1",
        "https://api.deepseek.com/v1?api_key=secret",
        "https://api.deepseek.com/../admin",
        "https://api.deepseek.com/v1#secret",
    ],
)
def test_untrusted_destinations_are_rejected_before_network(registry, url):
    with pytest.raises(StudyError, match="MODEL_(ORIGIN_NOT_ALLOWED|BASE_URL_INVALID)"):
        save(registry, connection={"base_url": url})


def test_new_destination_requires_explicit_credential_and_edit_version(registry):
    saved = save(registry)
    with pytest.raises(StudyError, match="MODEL_KEY_REQUIRED_FOR_NEW_URL"):
        save(registry, **saved, connection={"base_url": "https://api.deepseek.com/v1", "api_key": None})
    changed = save(registry, **saved, connection={"api_key": "replacement"})
    with pytest.raises(StudyError, match="MODEL_VERSION_CONFLICT"):
        save(registry, **saved)
    route(registry, saved["connection_id"])
    with pytest.raises(StudyError, match="MODEL_CONNECTION_IN_USE"):
        command(registry, "DELETE", **changed)
    save(registry, **changed, connection={"enabled": False})
    with pytest.raises(StudyError, match="MODEL_BINDING_UNAVAILABLE"):
        registry[0].freeze(registry[1])
    command(registry, "CLEAR_ROUTES")
    assert command(registry, "DELETE", connection_id=saved["connection_id"], version=3)["deleted"]
    with pytest.raises(StudyError, match="MODEL_ROUTE_REQUIRED"):
        registry[0].freeze(registry[1])


def test_saved_run_uses_original_models_and_credentials_after_connection_edit(registry, monkeypatch):
    reg, owner = registry
    saved = save(registry)
    route(registry, saved["connection_id"])
    store = StudyStore(reg.store.dsn, reg.freeze)
    runtime = StudyRuntime(store, Authority(), RegistryProvider(reg))
    runtime.initialize()
    scope = {"owner_id": owner, "course_id": "models-" + uuid.uuid4().hex, "revision": 1}
    scope["session_id"] = store.command(
        StudyCommand(**scope, operation="CREATE_SESSION", request_key="session"), "real"
    )["session_id"]
    start = StudyCommand(
        **scope, operation="START", request_key="run", goal="Explain stopping conditions and create practice"
    )
    public = store.command(start, "real")
    assert public["run"]["model_selection"]["review"]["model"] == "critic"
    assert "credential" not in json.dumps(public, default=str)
    save(registry, **saved, connection={"api_key": "new-key", "enabled": False})
    assert (
        store.command(start, "real")["run"]["run_id"] == public["run"]["run_id"]
    )  # Idempotent even after disable.
    seen = []

    def handler(request):
        data = json.loads(request.content)
        seen.append((data["model"], request.headers["authorization"]))
        call = (
            {
                "name": "assess_study_candidate",
                "arguments": {
                    "explanation": {"issue": "none", "correction": "", "anchors": []},
                    "questions": [
                        {"answer": "A stopping condition", "issue": "none", "evidence": ["e1"]},
                        {"answer": "A stopping condition", "issue": "none", "evidence": ["e1"]},
                    ],
                },
            }
            if data["model"] == "critic"
            else MockProvider().decide(data["messages"], 10)
        )
        if data["model"] == "critic":
            body = json.loads(data["messages"][-1]["content"])
            if body.get("review_mode") == "independent_solution":
                call["arguments"] = {
                    "questions": [
                        {"answer": "A stopping condition", "evidence": ["e1"]},
                        {"answer": "A stopping condition", "evidence": ["e1"]},
                    ]
                }
            elif "fields" in body:
                assert data["max_tokens"] == 1200
                call["arguments"] = {
                    "explanation_checks": [
                        {
                            "id": c["id"],
                            "course_fact": body["passages"][0]["text"][:120],
                            "evidence_ids": [body["fields"][0]["own_evidence"][0]["evidence_id"]],
                            "supported": True,
                        }
                        for c in body["explanation_claims"]
                    ],
                    "goal_checks": [
                        {"id": c["id"], "observation": "Satisfies the goal", "matches": True}
                        for c in body["goal_constraints"]
                    ],
                    "checks": [
                        {
                            "field": field["field"],
                            "course_fact": "Recursion needs a stopping condition.",
                            "evidence_ids": [field["own_evidence"][0]["evidence_id"]],
                            "issue": "none",
                            "correction": "",
                            **(
                                {"answer_check": {"answer": "A stopping condition", "matches": True}}
                                if "answer_points" in field
                                else {}
                            ),
                        }
                        for field in body["fields"]
                    ],
                }
                call["arguments"].update({c.pop("field"): c for c in call["arguments"].pop("checks")})
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
                                        "name": call["name"],
                                        "arguments": json.dumps(call["arguments"]),
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        )

    client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs)
    )
    run = next(r for r in store.candidates() if r["run_id"] == public["run"]["run_id"])
    runtime.execute(run)
    result = store.command(StudyCommand(**scope, operation="READ"), "real")
    assert result["run"]["status"] == "succeeded"
    assert [model for model, _ in seen] == ["generator", "generator", "generator", "critic"]
    assert all(key == "Bearer private-provider-key" for _, key in seen)
    events = store.command(StudyCommand(**scope, operation="EVENTS"), "real")["events"]
    assert "private-provider-key" not in json.dumps(events)
    assert all(
        e["payload"]["model_selection"]["version"] == 1 for e in events if e["event_type"] == "model_started"
    )


def test_probe_and_discovery_use_saved_credentials_and_hide_remote_errors(registry, monkeypatch):
    saved = save(registry)
    client = httpx.Client

    def handler(request):
        assert request.headers["authorization"] == "Bearer private-provider-key"
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "remote-model"}]})
        return httpx.Response(401, text="REMOTE SECRET private-provider-key")

    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs)
    )
    assert command(registry, "DISCOVER", **saved)["model_ids"] == ["remote-model"]
    check = command(registry, "PROBE", **saved, model="generator")["check"]
    assert check["ok"] is False
    assert "private-provider-key" not in json.dumps(check)
    assert command(registry, "LIST")["connections"][0]["checks"]["generator"] == check


def test_late_probe_result_does_not_certify_changed_connection(registry, monkeypatch):
    saved = save(registry)
    client = httpx.Client

    def handler(request):
        save(registry, **saved, connection={"api_key": "new-key"})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {"name": "connection_check", "arguments": '{"ok":true}'},
                                }
                            ]
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs)
    )
    with pytest.raises(StudyError, match="MODEL_VERSION_CONFLICT"):
        command(registry, "PROBE", **saved, model="generator")
    assert command(registry, "LIST")["connections"][0]["checks"] == {}


def test_models_http_requires_path_bound_study_signature_and_redacts_validation(registry):
    reg, owner = registry
    path = "/internal/v1/models/command"
    timestamp = str(int(time.time()))
    body = json.dumps({"owner_id": owner, "operation": "LIST"}).encode()
    headers = {
        "X-LectureLens-Timestamp": timestamp,
        "X-LectureLens-Signature": signature(SECRET, timestamp, body, path),
    }
    with TestClient(create_app(SimpleNamespace(), SECRET, model_registry=reg)) as client:
        assert client.post(path, content=body).status_code == 401
        result = client.post(path, content=body, headers=headers)
        assert result.status_code == 200 and result.json()["owner_id"] == owner
        headers["X-LectureLens-Signature"] = retrieval_signature(SECRET, timestamp, body, path)
        assert client.post(path, content=body, headers=headers).status_code == 401
        body = json.dumps(
            {"owner_id": owner, "operation": "SAVE", "connection": {"api_key": "private-input"}}
        ).encode()
        headers["X-LectureLens-Signature"] = signature(SECRET, timestamp, body, path)
        result = client.post(path, content=body, headers=headers)
        assert result.status_code == 422 and "private-input" not in result.text


def test_discovery_keeps_large_catalog_without_saving_models(registry, monkeypatch):
    saved = save(registry)
    client = httpx.Client
    ids = [f"remote-model-{index}" for index in range(140)]
    payload = {"data": [{"id": model} for model in ids + ids[:5]] + [{"id": "bad id"}, None]}
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)), **kwargs
        ),
    )
    result = command(registry, "DISCOVER", **saved)
    assert result["model_ids"] == ids
    assert result["total_count"] == 140
    assert result["skipped_count"] == 2
    assert result["truncated"] is False
    assert command(registry, "LIST")["connections"][0]["model_ids"] == ["generator", "critic"]


def test_discovery_reports_truncation_and_provider_pagination():
    from lecturelens_agent.study.models import discovery_catalog

    result = discovery_catalog({"data": [{"id": f"model-{i}"} for i in range(1003)], "has_more": True})
    assert len(result["model_ids"]) == 1000
    assert result["total_count"] == 1003
    assert result["truncated"] is True
    assert result["provider_has_more"] is True
    with pytest.raises(StudyError):
        discovery_catalog({"data": {"id": "not-a-list"}})


def test_managed_pilot_uses_isolated_routes_and_never_changes_source_config(registry, monkeypatch, tmp_path):
    import importlib.util
    import sys
    from pathlib import Path

    import lecturelens_agent

    reg, owner = registry
    saved = save(
        registry,
        connection={
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model_ids": ["qwen-plus", "qwen3-max"],
        },
    )
    command(
        registry,
        "ROUTE",
        bindings={
            role: {"connection_id": saved["connection_id"], "model": model}
            for role, model in [("decision", "qwen-plus"), ("review", "qwen3-max")]
        },
    )
    before = command(registry, "LIST")
    config = tmp_path / "deployment.json"
    config.write_text(json.dumps({"AGENT_DATABASE_URL": reg.store.dsn, "AGENT_SERVICE_SECRET": SECRET}))
    cases = tmp_path / "cases.json"
    cases.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "test-absent",
                        "split": "development",
                        "goal": "Explain quantum field theory from these passages",
                    }
                ]
            }
        )
    )
    output = tmp_path / "pilot"
    package = output / "src/lecturelens_agent"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    monkeypatch.setattr(lecturelens_agent, "__file__", str(package / "__init__.py"))
    script = Path(__file__).resolve().parents[2] / "scripts/eval/pilot-managed-study.py"
    spec = importlib.util.spec_from_file_location("managed_pilot", script)
    pilot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pilot)
    monkeypatch.setattr(
        pilot.replay,
        "captions",
        lambda source, path: [
            {
                "evidence_id": "caption-1",
                "text": "Functions without return yield None.",
                "start_ms": 0,
                "end_ms": 1000,
                "source_type": "SUBTITLE",
            }
        ],
    )
    monkeypatch.setenv("AGENT_DATABASE_URL", reg.store.dsn)
    monkeypatch.setenv("AGENT_SERVICE_SECRET", SECRET)
    calls = []

    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        choice = payload["tool_choice"]
        name = choice["function"]["name"] if isinstance(choice, dict) else "report_insufficient_evidence"
        arguments = {
            "search_course_evidence": {"query": "quantum field theory"},
            "report_insufficient_evidence": {
                "reason": "Retrieved passages do not discuss quantum field theory."
            },
            "assess_study_candidate": {
                "course_fact": "Functions without return yield None; quantum field theory is absent.",
                "evidence_ids": ["e1"],
                "support": "absent",
                "missing_goal_quote": "quantum field theory",
            },
        }[name]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {"name": name, "arguments": json.dumps(arguments)},
                                }
                            ]
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs)
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(script),
            "--runtime-config",
            str(config),
            "--owner-id",
            str(owner),
            "--cases",
            str(cases),
            "--output",
            str(output),
        ],
    )
    pilot.main()
    row = json.loads((output / "results.jsonl").read_text())
    assert row["run"]["status"] == "succeeded"
    assert row["artifact"]["kind"] == "insufficient_evidence"
    assert [call["model"] for call in calls] == ["qwen-plus", "qwen-plus", "qwen3-max"]
    assert command(registry, "LIST") == before
    assert "private-provider-key" not in (output / "results.jsonl").read_text()
    with reg.store.connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM study_run WHERE run_id=%s", (row["run"]["run_id"],)
            ).fetchone()["n"]
            == 0
        )
    with pytest.raises(FileExistsError):
        pilot.main()
    assert len(calls) == 3
