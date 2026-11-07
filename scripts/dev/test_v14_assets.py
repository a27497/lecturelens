"""Source restoration and formatter fences through the frozen v14 entry; offline only."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval/tutor-v14-fresh-v1"))
import run_fresh as E  # noqa: E402 -- exercise the actual frozen entry, not a replacement

C = E.contract
RUFF = ROOT / "agent-service/.venv/bin/ruff"
BASE_SHA = "e4699e8e9144df50482eb671f89cebd1bf07cdf8"
ORIGINAL_SHA = "59ad81e33ec8881f3a8bafb8f220ec5b9bea8af6e9caee7fbdefffaa703ffc53"
REJECTED_SHA = "dd472a2a972b5b25a24b120a9da4ce8a79cdd3e3df89ace7e62873894c02c206"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    output = Path(os.environ["V14_ASSET_CHECK_OUTPUT"])
    output.mkdir(parents=True, exist_ok=True)
    with (output / name).open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


@pytest.fixture(autouse=True)
def asset_offline(monkeypatch):
    assert os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") == "1"
    original = os.environ.get

    def get(key, *args):
        if key in {"AGENT_LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"}:
            pytest.fail("Credential lookup forbidden")
        return original(key, *args)

    monkeypatch.setattr(os.environ, "get", get)
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kw: pytest.fail("Real transport forbidden"))


def clone(tmp_path):
    target = tmp_path / "eval/tutor-v14-fresh-v1"
    shutil.copytree(C.HERE, target, ignore=shutil.ignore_patterns("__pycache__"))
    return target


def prepare():
    return E.parser().parse_args(["--agent", C.CANDIDATE, "--model", "deepseek-flash"])


def test_original_bytes_actual_entry_and_all_quotes():
    source = C.HERE / "materials/carpentries-python-new.md"
    retained = ROOT / ".data/tutor-v14-real-20261107/python-original-source.md"
    assert source.read_bytes() == retained.read_bytes() and digest(source) == ORIGINAL_SHA
    result = E.run(prepare())
    assert result["mode"] == "PREPARE_ONLY_NO_EGRESS"
    assert result["counts"] == dict(courses=2, sessions=4, turns=16, answerable=12, insufficient=4)
    assert result["candidate_sha256"] == C.verify_candidate()
    assert result["max_usd"] == "NEW_USER_AUTHORIZATION_REQUIRED"
    assert len(C.verify()[3]) == 16
    save("actual-entry-prepare.json", result)


@pytest.mark.parametrize(
    "material",
    [
        "carpentries-python-new.md",
        "carpentries-spreadsheets-new.md",
        "carpentries-python-LICENSE.md",
        "carpentries-spreadsheets-LICENSE.md",
    ],
)
def test_altered_original_rejected_by_actual_entry_before_db(tmp_path, monkeypatch, material):
    target = clone(tmp_path)
    source = target / "materials" / material
    source.write_bytes(source.read_bytes() + b"\nchanged\n")
    assert (target / "freeze-lock.json").read_bytes() == (C.HERE / "freeze-lock.json").read_bytes()
    monkeypatch.setattr(C, "HERE", target)
    monkeypatch.setattr(E.bridge.legacy, "Ledger", lambda *a, **k: pytest.fail("DB construction forbidden"))
    args = E.parser().parse_args(
        [
            "--mock",
            "--agent",
            C.CANDIDATE,
            "--model",
            "deepseek-flash",
            "--max-calls",
            "80",
            "--max-usd",
            "0.70",
            "--output",
            str(tmp_path / "refused"),
        ]
    )
    with pytest.raises(ValueError, match="V14_SOURCE_CHANGED"):
        E.run(args)
    assert not (tmp_path / "refused").exists()


def test_previous_formatted_bytes_rejected_without_hash_replacement(tmp_path, monkeypatch):
    target = clone(tmp_path)
    bad = subprocess.check_output(
        [
            "git",
            "show",
            BASE_SHA + ":eval/tutor-v14-fresh-v1/materials/carpentries-python-new.md",
        ],
        cwd=ROOT,
    )
    assert hashlib.sha256(bad).hexdigest() == REJECTED_SHA
    (target / "materials/carpentries-python-new.md").write_bytes(bad)
    monkeypatch.setattr(C, "HERE", target)
    with pytest.raises(ValueError, match="V14_SOURCE_CHANGED"):
        E.run(prepare())


def test_reproduce_original_directory_formatter_defect_in_scratch(tmp_path):
    source = tmp_path / "python-original.md"
    source.write_bytes((C.HERE / "materials/carpentries-python-new.md").read_bytes())
    config = tmp_path / "original-pyproject.toml"
    config.write_bytes(
        subprocess.check_output(["git", "show", BASE_SHA + ":agent-service/pyproject.toml"], cwd=ROOT)
    )
    result = subprocess.run(
        [str(RUFF), "format", "--config", str(config), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0 and digest(source) == REJECTED_SHA
    save(
        "formatter-defect-reproduced.json",
        dict(
            command=result.args,
            stdout=result.stdout,
            original_sha256=ORIGINAL_SHA,
            actual_formatted_sha256=digest(source),
            scratch_only=True,
        ),
    )


@pytest.mark.parametrize("mode", ["explicit-config-directory", "discovered-config", "explicit-files"])
def test_formatter_preserves_downloads_and_all_frozen_assets(tmp_path, mode):
    target = clone(tmp_path)
    config = tmp_path / "agent-service/pyproject.toml"
    config.parent.mkdir()
    config.write_bytes((ROOT / "agent-service/pyproject.toml").read_bytes())
    (tmp_path / "eval/ruff.toml").write_bytes((ROOT / "eval/ruff.toml").read_bytes())
    # Unformatted frozen-code sentinel ensures exclusion rather than idempotence.
    (target / "protected.py").write_text("sentinel=  1\n")
    private = tmp_path / ".data"
    private.mkdir()
    (private / "record.py").write_text("record=  1\n")
    paths = [*target.rglob("*"), private / "record.py"]
    before = {str(p): digest(p) for p in paths if p.is_file()}
    command = [str(RUFF), "format"]
    if mode != "discovered-config":
        command += ["--config", str(config)]
    if mode == "explicit-files":
        command += [
            str(target / "materials/carpentries-python-new.md"),
            str(target / "protected.py"),
            str(private / "record.py"),
        ]
    else:
        command += [str(target)]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert before == {path: digest(Path(path)) for path in before}
    save(
        "formatter-protected-" + mode + ".json",
        dict(
            command=command,
            stdout=result.stdout,
            stderr=result.stderr,
            protected_files=len(before),
            all_hashes_unchanged=True,
            scratch_only=True,
        ),
    )


def test_explicit_nonfrozen_code_still_formats(tmp_path):
    config = tmp_path / "agent-service/pyproject.toml"
    config.parent.mkdir()
    config.write_bytes((ROOT / "agent-service/pyproject.toml").read_bytes())
    script = tmp_path / "scripts/dev/check.py"
    script.parent.mkdir(parents=True)
    script.write_text("answer=  1\n")
    subprocess.run(
        [str(RUFF), "format", "--config", str(config), str(script)], check=True, capture_output=True
    )
    assert script.read_text() == "answer = 1\n"


def test_actual_cli_prepare_only_and_live_rejected_without_egress(tmp_path):
    command = [
        sys.executable,
        str(C.HERE / "run_fresh.py"),
        "--agent",
        C.CANDIDATE,
        "--model",
        "deepseek-flash",
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    prepared = json.loads(result.stdout)
    assert prepared["mode"] == "PREPARE_ONLY_NO_EGRESS" and prepared["counts"]["turns"] == 16
    blocked = subprocess.run(
        [
            *command,
            "--live",
            "--max-calls",
            "80",
            "--max-usd",
            "0.70",
            "--output",
            str(tmp_path / "never-send"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert blocked.returncode == 2 and not (tmp_path / "never-send").exists()
    assert json.loads(blocked.stdout)["error"] == "V14_FRESH_PREFLIGHT_OR_STARTUP_REJECTED"
    save(
        "actual-cli.json",
        dict(command=command, prepare_exit=0, prepared=prepared, live_under_fence_exit=2, real_calls=0),
    )


def test_live_opt_in_is_not_implied_by_restoration(tmp_path, monkeypatch):
    monkeypatch.delenv("LECTURELENS_REAL_EVAL", raising=False)
    args = E.parser().parse_args(
        [
            "--live",
            "--agent",
            C.CANDIDATE,
            "--model",
            "deepseek-flash",
            "--max-calls",
            "80",
            "--max-usd",
            "0.70",
            "--output",
            str(tmp_path / "no-grant"),
        ]
    )
    with pytest.raises(E.bridge.legacy.EvalError, match="REAL_EVAL_SWITCH_REQUIRED"):
        E.preflight(args)
    assert not (tmp_path / "no-grant").exists()
