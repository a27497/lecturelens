"""Real loopback Vue/Java/Python preview using the repository's isolated smoke infrastructure."""

import argparse
import importlib.util
import json
import os
import secrets
import shutil
import signal
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "p9_smoke", ROOT / "scripts/ci/mock-study-tutor-e2e.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.DEMO = "lecturelens-demo-p9preview"
m.AGENT = "lecturelens-agent-p9preview"
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
a = parser.parse_args()
a.output = a.output.resolve()


class Preview(m.Smoke):
    def login(self):
        self.credentials = {
            "email": f"p9-preview-{secrets.token_hex(8)}@example.invalid",
            "password": secrets.token_hex(20) + "A1",
        }
        self.private.append(self.credentials["password"])
        self.api("POST", "/api/auth/register", self.credentials)
        self.token = self.api("POST", "/api/auth/login", self.credentials)[
            "accessToken"
        ]
        self.private.append(self.token)

    def start_agent(self):
        self.env["STUDY_FEEDBACK_ENABLED"] = "true"
        self.env["PYTHONPATH"] += os.pathsep + str(ROOT / "eval/p9-choice")
        process = self.spawn(
            [
                "uv",
                "run",
                "--offline",
                "--no-sync",
                "uvicorn",
                "preview_app:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.result["ports"]["AGENT_HTTP_PORT"]),
            ],
            "agent",
            ROOT / "agent-service",
        )
        self.health(process, self.agent_base, "/healthz")
        return process


s = Preview(
    argparse.Namespace(
        output_dir=a.output / "stack", legacy_only=False, embedding_cache_source=None
    )
)
s.result["not_run"] = [
    "real-model task quality",
    "Tutor evaluation",
    "load tests",
    "mobile-specific acceptance",
]
success = False
browser_tmp = None
signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
try:
    with s.stage("preflight"):
        s.preflight()
        assert s.jar.is_file(), "Build Java before acceptance"
        s.result["source_dirty"] = bool(
            s.capture(["git", "status", "--porcelain", "--untracked-files=normal"])
        )
    with s.stage("infrastructure"):
        s.infrastructure()
    with s.stage("Java"):
        s.java()
    with s.stage("PostgreSQL"):
        s.owned.append(m.AGENT)
        s.run(
            s.compose(m.AGENT, "up", "-d", "--wait", "--wait-timeout", "90"),
            "pg-up",
            100,
        )
    with s.stage("Agent"):
        s.start_agent()
    with s.stage("synthetic-course"):
        s.course()
    with s.stage("Vue-preview"):
        port = s.free_port(0)
        s.env["VITE_BACKEND_PROXY_TARGET"] = s.base
        process = s.spawn(
            [
                "/opt/node/bin/npm",
                "run",
                "preview",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--strictPort",
            ],
            "vue",
            ROOT / "frontend",
        )
        s.health(process, f"http://127.0.0.1:{port}", "/")
        s.env.update(
            PREVIEW_URL=f"http://127.0.0.1:{port}",
            PREVIEW_EMAIL=s.credentials["email"],
            PREVIEW_PASSWORD=s.credentials["password"],
            PREVIEW_TASK=s.task,
            PREVIEW_SHA=s.result["head"],
            PREVIEW_EVIDENCE=str(a.output),
            PREVIEW_DIRTY=str(s.result["source_dirty"]).lower(),
        )
    with s.stage("browser"):
        browser_tmp = tempfile.mkdtemp(prefix="p9b-")
        s.env["TMPDIR"] = browser_tmp
        s.run(
            ["/opt/node/bin/node", str(ROOT / "eval/p9-choice/browser.mjs")],
            "browser",
            420,
        )
    with s.stage("database-mock-proof"):
        s.result["database"] = json.loads(
            s.sql(
                "SELECT json_build_object('runs',(SELECT count(*) FROM study_run),'non_mock',(SELECT count(*) FROM study_run WHERE model_mode<>'mock' OR model_config IS NOT NULL),'model_connections',(SELECT count(*) FROM agent_model_connection),'choice_attempts',(SELECT count(*) FROM study_attempt WHERE selected_option_id IS NOT NULL),'open_attempts',(SELECT count(*) FROM study_attempt WHERE selected_option_id IS NULL),'broken_choice_pairs',(SELECT count(*) FROM study_attempt WHERE (selected_option_id IS NULL) <> (choice_result IS NULL)))",
                pg=True,
            )
        )
        assert (
            s.result["database"]["non_mock"]
            == s.result["database"]["model_connections"]
            == s.result["database"]["broken_choice_pairs"]
            == 0
        )
        assert not (s.out / "denied-network.log").exists()
        s.result["mysql_course"] = s.sql("SELECT id,status,user_id FROM analysis_task")
        s.result["mode"] = (
            "AGENT_LLM_MODE=mock; STUDY_FEEDBACK_ENABLED=true; offline hash embedding; real product Mock choice generator and program grader"
        )
    success = True
except BaseException as error:  # noqa: BLE001 -- retain failure and clean only this preview's resources
    s.result["failure"] = s.redact(str(error))
    print("FAIL " + s.redact(str(error)), flush=True)
finally:
    try:
        with s.stage("cleanup"):
            s.cleanup()
    except BaseException as error:  # noqa: BLE001 -- retain failure and clean only this preview's resources
        success = False
        s.result["cleanup_failure"] = s.redact(str(error))
    if browser_tmp:
        shutil.rmtree(browser_tmp)
    s.result["success"] = success
    s.save()
sys.exit(0 if success else 1)
