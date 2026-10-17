"""Serial whole-lecture trials through the unmodified production HTTP pipeline."""

import argparse
import hashlib
import json
import math
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
REPORT = Path(__file__).resolve().parent
BATCH = REPORT / "batch-v2"
PRIVATE = ROOT / ".data/baseline-asr-20261015"


def utc():
    return datetime.now(timezone.utc).isoformat()


def append(path, value):
    with path.open("a") as output:
        output.write(json.dumps(value, ensure_ascii=False) + "\n")


def api(client, method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    if response.status_code == 401 and not path.startswith("/api/auth/"):
        login(client)
        response = client.request(method, path, **kwargs)
    response.raise_for_status()
    value = response.json()
    if value.get("code") not in ("OK", "SUCCESS", "0", 0, 200, None):
        raise RuntimeError(f"API failure: {path}: {value.get('code')}")
    return value.get("data", value)


def login(client):
    credentials_file = PRIVATE / "account.json"
    if credentials_file.exists():
        credentials = json.loads(credentials_file.read_text())
    else:
        credentials = {
            "email": f"baseline-asr-{secrets.token_hex(6)}@example.com",
            "password": "Eval9" + secrets.token_hex(20),
        }
        api(client, "POST", "/api/auth/register", json=credentials)
        credentials_file.write_text(json.dumps(credentials) + "\n")
        credentials_file.chmod(0o600)
    result = api(client, "POST", "/api/auth/login", json=credentials)
    client.headers["Authorization"] = "Bearer " + result["accessToken"]


def upload(client, source):
    media = ROOT / source["evaluation_video_file"]
    if (
        hashlib.file_digest(media.open("rb"), "sha256").hexdigest()
        != source["evaluation_video_sha256"]
    ):
        raise ValueError("Frozen media changed")
    size = media.stat().st_size
    chunk_size = 8 * 1024 * 1024
    count = math.ceil(size / chunk_size)
    upload_id = api(
        client,
        "POST",
        "/api/uploads/sessions",
        json={
            "filename": media.name,
            "sizeBytes": size,
            "chunkSizeBytes": chunk_size,
            "totalChunks": count,
            "fileMd5": hashlib.file_digest(media.open("rb"), "md5").hexdigest(),
        },
    )["uploadId"]
    with media.open("rb") as stream:
        for index in range(count):
            api(
                client,
                "POST",
                f"/api/uploads/sessions/{upload_id}/chunks/{index}",
                files={"file": (media.name, stream.read(chunk_size), "video/mp4")},
            )
    api(client, "POST", f"/api/uploads/sessions/{upload_id}/complete")
    return upload_id


def run_trial(client, source, trial_id, events):
    marker = {"trial_id": trial_id, "source_id": source["id"]}
    (PRIVATE / "active-trial.json").write_text(json.dumps(marker) + "\n")
    uploaded_at = utc()
    upload_started = time.monotonic()
    upload_id = upload(client, source)
    upload_ms = (time.monotonic() - upload_started) * 1000
    started_at, started = utc(), time.monotonic()
    task = api(
        client,
        "POST",
        "/api/tasks",
        json={"uploadId": upload_id, "sourceLanguage": "en", "targetLanguage": "zh-CN"},
    )
    task_id = task["taskId"]
    row = dict(
        marker,
        phase="submitted",
        task_id=task_id,
        upload_id=upload_id,
        upload_started_at_utc=uploaded_at,
        submitted_at_utc=started_at,
        upload_ms=round(upload_ms, 3),
    )
    append(events, row)
    print("submitted", trial_id, task_id, flush=True)
    status = None
    while time.monotonic() - started < 4 * 3600:
        task = api(client, "GET", f"/api/tasks/{task_id}")
        if task["status"] in {"SUCCEEDED", "FAILED", "CANCELED"}:
            status = task["status"]
            break
        time.sleep(1)
    if status is None:
        raise RuntimeError("Four-hour trial observation timeout; do not resubmit")
    task_terminal_ms = round((time.monotonic() - started) * 1000, 3)
    result = api(client, "GET", f"/api/tasks/{task_id}/results")
    # Keep only public-course transcription and accounting fields, no login or
    # unrelated application data. Failed observations remain in the raw records.
    prediction = {
        k: result.get(k)
        for k in (
            "taskId",
            "sourceFullText",
            "subtitles",
            "translationStatus",
            "aiCallRecords",
        )
    }
    output = BATCH / "predictions" / (trial_id + ".json")
    output.parent.mkdir(exist_ok=True)
    with output.open("x") as stream:
        stream.write(json.dumps(prediction, ensure_ascii=False, indent=2) + "\n")
    index_status = None
    if status == "SUCCEEDED":
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            index_status = api(
                client, "GET", f"/api/tasks/{task_id}/evidence/index-status"
            )
            if index_status.get("status", index_status.get("state")) == "READY":
                break
            time.sleep(1)
    row.update(
        phase="finished",
        finished_at_utc=utc(),
        task=task,
        task_terminal_ms=task_terminal_ms,
        processing_to_index_ms=round((time.monotonic() - started) * 1000, 3),
        index_status=index_status,
        prediction_file=str(output.relative_to(ROOT)),
    )
    append(events, row)
    print("finished", trial_id, status, row["processing_to_index_ms"], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8089")
    parser.add_argument("--trials", type=int, default=2)
    args = parser.parse_args()
    if args.base_url != "http://127.0.0.1:8089":
        raise ValueError("Use the isolated local evaluation backend")
    BATCH.mkdir(exist_ok=True)
    events = BATCH / "trials.jsonl"
    prior = (
        [json.loads(line) for line in events.read_text().splitlines()]
        if events.exists()
        else []
    )
    completed = {r["trial_id"] for r in prior if r["phase"] == "finished"}
    pending = {r["trial_id"] for r in prior if r["phase"] == "submitted"} - completed
    if pending:
        raise ValueError(
            f"Unobserved submitted tasks require read-only recovery, never resubmit: {sorted(pending)}"
        )
    manifest = json.loads((REPORT / "assets.lock.json").read_text())
    with httpx.Client(base_url=args.base_url, timeout=180, trust_env=False) as client:
        login(client)
        for repeat in range(1, args.trials + 1):
            for source in manifest["sources"]:
                trial_id = f"v2-{source['id']}-{repeat}"
                if trial_id not in completed:
                    calls_path = BATCH / "http-calls.jsonl"
                    calls = (
                        [
                            json.loads(line)
                            for line in calls_path.read_text().splitlines()
                        ]
                        if calls_path.exists()
                        else []
                    )
                    asr = [c for c in calls if c["kind"] == "asr"]
                    if any(
                        c.get("http_status") == 200 and c.get("usage") is None
                        for c in asr
                    ):
                        raise RuntimeError(
                            "Stop before next trial: preceding paid ASR usage unavailable"
                        )
                    spent = sum(
                        (
                            (c.get("usage") or {}).get("input_tokens", 0) * 0.8
                            + (c.get("usage") or {}).get("output_tokens", 0) * 2.7
                        )
                        / 1_000_000
                        for c in asr
                    )
                    unknown_reserve = sum(c.get("usage") is None for c in asr)
                    if spent + unknown_reserve + 3 > 15:
                        raise RuntimeError(
                            "Stop before next trial: conservative unknown-call reserve plus 15 CNY headroom"
                        )
                    run_trial(client, source, trial_id, events)


if __name__ == "__main__":
    main()
