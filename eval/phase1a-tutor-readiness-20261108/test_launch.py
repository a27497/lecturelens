"""Handoff tests replace exec and admission; no live entry is invoked."""

import json

import launch
import pytest


def test_missing_runtime_key_stops_before_inspection_claim_or_reservation(
    monkeypatch, tmp_path
):
    monkeypatch.delenv("AGENT_LLM_API_KEY", raising=False)
    monkeypatch.setattr(
        launch, "inspect", lambda _: pytest.fail("must stop before inspection")
    )
    with pytest.raises(ValueError, match="RUNTIME_KEY_NOT_INJECTED"):
        launch.handoff(tmp_path, tmp_path / "output", None, None)


@pytest.mark.parametrize(
    "change", ["none", "head", "root", "cost", "reviewer", "output"]
)
def test_only_bound_admission_can_handoff_without_reading_or_copying_key(
    monkeypatch, tmp_path, change
):
    # Synthetic environment membership only; never inspect real caller variables.
    monkeypatch.setenv("AGENT_LLM_API_KEY", "synthetic-not-a-provider-key")
    original = launch.os.environ.get

    def guarded(key, *args):
        if key == "AGENT_LLM_API_KEY":
            pytest.fail("launcher must not read a credential value")
        return original(key, *args)

    monkeypatch.setattr(launch.os.environ, "get", guarded)
    monkeypatch.setattr(launch, "inspect", lambda _: {"frozen": {"synthetic": True}})
    monkeypatch.setattr(launch, "preparation_head", lambda: "synthetic-head")
    from lecturelens_real_eval.tutor import selection_smoke

    admissions = []
    monkeypatch.setattr(
        selection_smoke, "live_admission", lambda *args: admissions.append(args)
    )
    grant = dict(
        preparation_git_head="synthetic-head",
        execution_root=str(tmp_path),
        supplier_cost_risk_accepted=True,
        independent_reviewer="synthetic coordinator",
    )
    if change in {"head", "root", "cost", "reviewer"}:
        field = {
            "head": "preparation_git_head",
            "root": "execution_root",
            "cost": "supplier_cost_risk_accepted",
            "reviewer": "independent_reviewer",
        }[change]
        grant[field] = None
    receipt = tmp_path / "synthetic-grant.json"
    receipt.write_text(json.dumps(grant))
    output = tmp_path / ".data/output"
    if change == "output":
        output.mkdir(parents=True)
    calls = []
    if change == "none":
        launch.handoff(
            tmp_path, output, receipt, receipt, execute=lambda *args: calls.append(args)
        )
        assert len(calls) == len(admissions) == 1
        assert "--mode" in calls[0][1] and "live" in calls[0][1]
        # os.execv takes no environment mapping; inheritance is native and the
        # frozen CLI alone owns the eventual, separately authorized dispatch.
        assert len(calls[0]) == 2
    else:
        with pytest.raises(ValueError):
            launch.handoff(
                tmp_path,
                output,
                receipt,
                receipt,
                execute=lambda *args: calls.append(args),
            )
        assert not calls and not admissions
