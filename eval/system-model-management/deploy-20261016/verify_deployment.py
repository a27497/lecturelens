"""Read-only local deployment checks. JWTs exist only in memory; no provider requests."""
from pathlib import Path
import base64, datetime, hashlib, hmac, json, re, shutil, ssl, subprocess, sys, time
import urllib.request, urllib.error

ROOT = Path(__file__).resolve().parents[3]
PUBLIC = Path(__file__).resolve().parent
PRIVATE = ROOT / ".data/system-model-management/deploy-20261016"

def service(unit):
    return dict(line.split("=", 1) for line in subprocess.check_output(
        ["systemctl", "show", unit, "-p", "MainPID", "-p", "ActiveState", "-p", "ExecMainStartTimestamp"], text=True
    ).splitlines() if "=" in line)

def environment(pid):
    return dict(item.decode().split("=", 1) for item in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0") if b"=" in item)

def main():
    before = json.loads((PUBLIC / "preflight.json").read_text())
    backend = service("lecturelens-live-backend")
    assert backend["ActiveState"] == "active"
    env = environment(backend["MainPID"])
    master = base64.b64decode(env["SYSTEM_MODEL_MASTER_KEY"], validate=True)
    assert len(master) == 32
    assert env["SYSTEM_MODEL_CONFIG_ENABLED"] == "true"
    assert env["SYSTEM_MODEL_PROBE_ALLOWED_ORIGINS"] == "https://api.deepseek.com"
    assert PRIVATE.stat().st_mode & 0o777 == 0o700
    assert (PRIVATE / "system-models.env").stat().st_mode & 0o777 == 0o600
    old_fingerprints = json.loads((PRIVATE / "before-environment.fingerprints.json").read_text())
    fingerprints = {k: hmac.new(master, v.encode(), hashlib.sha256).hexdigest() for k, v in env.items()}
    asr_names = sorted(k for k in old_fingerprints if k.startswith(("ASR_", "BAILIAN_", "SILICONFLOW_")))
    assert all(fingerprints.get(k) == old_fingerprints[k] for k in asr_names)
    preserved_services = {}
    for unit in ("lecturelens-live-agent", "lecturelens-live-model"):
        current = service(unit)
        assert current == before["services_before"][unit]
        preserved_services[unit] = current
    changed_env_names = sorted(k for k in set(fingerprints) | set(old_fingerprints) if fingerprints.get(k) != old_fingerprints.get(k))
    assert set(changed_env_names) <= {"SYSTEM_MODEL_MASTER_KEY", "SYSTEM_MODEL_CONFIG_ENABLED", "SYSTEM_MODEL_PROBE_ALLOWED_ORIGINS", "INVOCATION_ID", "JOURNAL_STREAM", "SYSTEMD_EXEC_PID"}
    def token(user_id):
        b64 = lambda value: base64.urlsafe_b64encode(value).rstrip(b"=")
        now = int(time.time())
        header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
        # Deliberately claim USER: authorization and /me must use the current database role.
        payload = b64(json.dumps({"sub": str(user_id), "type": "access", "role": "USER", "iat": now, "exp": now + 120}, separators=(",", ":")).encode())
        body = header + b"." + payload
        return (body + b"." + b64(hmac.new(env["JWT_ACCESS_SECRET"].encode(), body, hashlib.sha256).digest())).decode()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
    checked_responses = []
    def request(path, bearer=None, base="http://127.0.0.1:8080"):
        headers = {"Host": "34.81.153.182"} if base.startswith("https") else {}
        if bearer: headers["Authorization"] = "Bearer " + bearer
        req = urllib.request.Request(base + path, headers=headers)
        try:
            with opener.open(req, timeout=15) as response: code, body = response.status, response.read(2 * 1024 * 1024)
        except urllib.error.HTTPError as error: code, body = error.code, error.read(2 * 1024 * 1024)
        for key, value in env.items():
            if re.search(r"(?i)key|secret|password|token", key) and len(value) >= 8:
                assert value.encode() not in body, "Credential found in HTTP response; details withheld"
        assert not re.search(rb"v1\.[A-Za-z0-9_-]{30,}", body), "Ciphertext found in HTTP response"
        checked_responses.append({"path": path, "http_status": code, "bytes": len(body)})
        try:
            payload = json.loads(body)
            return code, payload.get("data", payload)
        except (ValueError, AttributeError): return code, body
    def sql(query):
        result = subprocess.run(["docker", "exec", "-i", "lecturelens-demo-l2-mysql-1", "sh", "-c", 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -u root -N -B courselingo'], input=query, text=True, capture_output=True)
        assert result.returncode == 0, "Database verification failed; details withheld"
        return result.stdout.splitlines()
    assert sql("SELECT version,success FROM flyway_schema_history ORDER BY installed_rank DESC LIMIT 1;") == ["25\t1"]
    assert sql("SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND trigger_name LIKE 'system_model%';") == ["4"]
    assert sql("SELECT role FROM user_account WHERE id=9;") == ["ADMIN"]
    assert sql("SELECT COUNT(*) FROM analysis_task WHERE status NOT IN ('SUCCEEDED','FAILED','CANCELED');") == ["0"]
    assert sql("SELECT COUNT(*) FROM system_model_provider UNION ALL SELECT COUNT(*) FROM system_model UNION ALL SELECT COUNT(*) FROM system_model_binding;") == ["0", "0", "0"]
    auth = token(9)
    assert request("/actuator/health")[1]["status"] == "UP"
    code, me = request("/api/me", auth)
    assert code == 200 and me["role"] == "ADMIN" and me["userId"] == 9
    assert request("/api/admin/system-models/catalog")[0] == 401
    ordinary = sql("SELECT id FROM user_account WHERE status='ACTIVE' AND role='USER' ORDER BY id LIMIT 1;")
    assert ordinary, "No existing ordinary account for 403 check"
    assert request("/api/admin/system-models/catalog", token(int(ordinary[0])))[0] == 403
    code, catalog = request("/api/admin/system-models/catalog", auth)
    assert code == 200 and not catalog["providers"] and not catalog["models"] and not catalog["bindings"]
    version = catalog["version"]
    code, status = request(f"/api/admin/system-models/status?version={version}", auth)
    assert code == 200 and status["version"] == version
    assert all(feature["source"] != "DATABASE" for feature in status["features"])
    code, policy = request("/api/admin/system-models/probe-policy", auth)
    assert code == 200 and policy["allowedOrigins"] == ["https://api.deepseek.com"]
    assert policy["timeoutMillis"] == 10000 and policy["concurrency"] == 2 and policy["responseLimitBytes"] == 65536
    assert request(f"/api/admin/system-models/versions/{version}", auth)[0] == 200
    sample_task = sql("SELECT id FROM analysis_task WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT 1;")[0]
    assert request("/api/admin/system-models/executions?taskId=" + sample_task, auth)[0] == 200
    assert request("/api/admin/system-models/audit", auth)[0] == 200
    assert request("/healthz", base="http://127.0.0.1:8090")[1]["status"] == "ready"
    assert request("/health", base="http://127.0.0.1:8091")[1]["status"] == "ok"
    assert request("/admin/settings/models", base="https://127.0.0.1")[0] == 200
    args = [item.decode() for item in Path(f"/proc/{backend['MainPID']}/cmdline").read_bytes().split(b"\0") if item]
    assert str(PRIVATE / "backend.jar") in args
    record = {
        "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "deployment_commit": before["deployment_commit"], "backend_jar_sha256": hashlib.sha256((PRIVATE / "backend.jar").read_bytes()).hexdigest(),
        "frontend_index_sha256": hashlib.sha256((ROOT / "frontend/dist/index.html").read_bytes()).hexdigest(),
        "flyway_version": 25, "config_version": version, "target_user_id": 9, "actual_me_role": me["role"],
        "token_claimed_role": "USER", "unauthenticated_status": 401, "ordinary_user_status": 403,
        "provider_count": 0, "model_count": 0, "binding_count": 0, "unfinished_analysis_tasks": 0,
        "backend_service": backend, "preserved_services": preserved_services,
        "disk_available_bytes": shutil.disk_usage(ROOT).free,
        "asr_environment_unchanged": True, "asr_environment_names": asr_names,
        "changed_environment_names": changed_env_names, "feature_status": status["features"],
        "probe_policy": policy, "http_checks": checked_responses,
        "responses_have_no_plaintext_credentials_or_ciphertext": True,
        "provider_calls": 0, "authenticated_verification": "120-second JWT kept only in process memory; no token or signing key persisted",
    }
    if "--record" in sys.argv:
        (PUBLIC / "verification.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"verification": "passed", "flyway": 25, "role": "ADMIN", "config_version": version, "provider_calls": 0}))

if __name__ == "__main__":
    try: main()
    except Exception as error:
        # Never echo exception messages, request headers, tokens or environment values.
        print("Deployment verification failed: " + type(error).__name__ + "; details withheld")
        raise SystemExit(1)
