"""Ten serial original-media trials; bounded, no configuration or task replay."""

import hashlib
import json
import math
import re
import subprocess
import time

import httpx
from support import PUBLIC, ROOT, admin, append, disk, redact, save, utc


def journal(since, task_id):
    p = subprocess.run(
        [
            "journalctl",
            "-u",
            "lecturelens-live-backend",
            "--since",
            since,
            "--no-pager",
            "-o",
            "cat",
        ],
        capture_output=True,
        text=True,
        timeout=25,
        check=True,
    )
    lines = [redact(line) for line in p.stdout.splitlines() if task_id in line]
    save("logs/" + task_id + ".json", lines, private=True)
    events = []
    for line in lines:
        match = re.search(
            r"event=pipeline_step_(completed|failed) taskId=(\S+) stepName=(\S+).*durationMillis=(\d+)",
            line,
        )
        if match:
            events.append(
                {"event": match[1], "step": match[3], "duration_ms": int(match[4])}
            )
        event = re.search(
            r"event=(llm_\S+|system_model_call_\S+|learning_package_llm_\S+)\s", line
        )
        if event:
            row = {"event": event[1]}
            for key, value in re.findall(r"\b([A-Za-z]+)=([^\s]+)", line):
                if key in {
                    "stepName",
                    "segmentCount",
                    "batchCount",
                    "batchSegmentCount",
                    "batchInputChars",
                    "durationMillis",
                    "wallDurationMillis",
                    "providerDurationMillis",
                    "totalTokens",
                    "retryCount",
                    "attempt",
                    "maxAttempts",
                    "httpStatus",
                    "providerErrorCategory",
                    "providerErrorCode",
                    "retryable",
                    "inputSource",
                    "inputLength",
                    "promptChars",
                    "responseFormatUsed",
                    "model",
                    "configVersion",
                    "category",
                    "timeoutMillis",
                    "maxTokens",
                }:
                    row[key] = int(value) if value.isdigit() else value
            events.append(row)
        retry = re.search(
            r"ASR chunk failed, retrying: taskId=([^,]+), chunkIndex=(\d+)/(\d+), attempt=(\d+)",
            line,
        )
        if retry:
            events.append(
                {
                    "event": "asr_retry",
                    "chunk": int(retry[2]),
                    "chunks": int(retry[3]),
                    "attempt": int(retry[4]),
                }
            )
    return events


def main():
    bridge = admin()
    manifest = json.loads(
        (ROOT / "eval/baseline-asr-20261015/assets.lock.json").read_text()
    )
    assert not (PUBLIC / "trials.jsonl").exists(), (
        "Existing trials: recover by task ID, never resubmit"
    )
    frozen = json.loads((PUBLIC / "binding-preflight.json").read_text())[
        "bound_version"
    ]
    save(
        "measurement-protocol.json",
        {
            "started_utc": utc(),
            "tasks": 10,
            "repeats": 2,
            "order": [x["id"] for x in manifest["sources"]],
            "task_limit_seconds": 1800,
            "serial": True,
            "target_language": "zh-CN",
            "base_url": "http://127.0.0.1:8080",
            "expected_config_version": frozen,
            "runtime_code_changed": False,
            "timeouts_or_concurrency_changed": False,
            "prices_cache_split_available": False,
        },
    )
    with httpx.Client(
        base_url="http://127.0.0.1:8080",
        timeout=180,
        trust_env=False,
        follow_redirects=False,
    ) as client:

        def api(method, path, **kwargs):
            client.headers["Authorization"] = "Bearer " + bridge.auth()
            response = client.request(method, path, **kwargs)
            if response.status_code >= 400:
                raise RuntimeError(f"Local API {path}: HTTP {response.status_code}")
            body = response.json()
            if body.get("code") not in ("OK", "SUCCESS", "0", 0, 200, None):
                raise RuntimeError("Local API error code: " + str(body.get("code")))
            return body.get("data", body)

        me = api("GET", "/api/me")
        save(
            "measurement-user.json",
            {"userId": me.get("userId"), "role": me.get("role")},
        )
        for repeat in [1, 2]:
            for source in manifest["sources"]:
                guard = disk()
                append("disk-observations.jsonl", guard)
                if guard["percent"] > 85:
                    save("STOP.json", {"reason": "DISK_ABOVE_85", "disk": guard})
                    return
                catalog = bridge.api("/admin/system-models/catalog")
                assert (
                    catalog["version"] == frozen
                    and catalog["effective"]["TRANSLATION_FULL_TEXT"]["source"]
                    == "DATABASE"
                    and catalog["effective"]["TRANSLATION_FULL_TEXT"]["model"]
                    == "deepseek-flash"
                ), "Configuration changed; stop"
                trial_id = f"deepseek-{source['id']}-{repeat}"
                path = ROOT / source["evaluation_video_file"]
                with path.open("rb") as stream:
                    assert (
                        hashlib.file_digest(stream, "sha256").hexdigest()
                        == source["evaluation_video_sha256"]
                    )
                with path.open("rb") as stream:
                    md5 = hashlib.file_digest(stream, "md5").hexdigest()
                upload_start = time.monotonic()
                size = path.stat().st_size
                chunk_size = 8 * 1024 * 1024
                chunks = math.ceil(size / chunk_size)
                upload = api(
                    "POST",
                    "/api/uploads/sessions",
                    json={
                        "filename": path.name,
                        "sizeBytes": size,
                        "chunkSizeBytes": chunk_size,
                        "totalChunks": chunks,
                        "fileMd5": md5,
                    },
                )["uploadId"]
                with path.open("rb") as stream:
                    for index in range(chunks):
                        if disk()["percent"] > 85:
                            save(
                                "STOP.json",
                                {
                                    "reason": "DISK_ABOVE_85_DURING_UPLOAD",
                                    "trial_id": trial_id,
                                    "upload_id": upload,
                                    "disk": disk(),
                                },
                            )
                            return
                        api(
                            "POST",
                            f"/api/uploads/sessions/{upload}/chunks/{index}",
                            files={
                                "file": (
                                    path.name,
                                    stream.read(chunk_size),
                                    "video/mp4",
                                )
                            },
                        )
                api("POST", f"/api/uploads/sessions/{upload}/complete")
                upload_ms = (time.monotonic() - upload_start) * 1000
                started = time.monotonic()
                created = utc()
                task = api(
                    "POST",
                    "/api/tasks",
                    json={
                        "uploadId": upload,
                        "sourceLanguage": "en",
                        "targetLanguage": "zh-CN",
                    },
                )
                task_id = task["taskId"]
                row = {
                    "trial_id": trial_id,
                    "source_id": source["id"],
                    "repeat": repeat,
                    "task_id": task_id,
                    "upload_id": upload,
                    "created_utc": created,
                    "upload_ms": upload_ms,
                    "source_sha256": source["evaluation_video_sha256"],
                    "phase": "submitted",
                }
                append("trials.jsonl", row)
                print(
                    json.dumps({"submitted": trial_id, "task_id": task_id}), flush=True
                )
                snapshot = bridge.api(
                    "/admin/system-models/executions?taskId=" + task_id
                )
                save("snapshots/" + trial_id + ".json", snapshot)
                assert snapshot and all(
                    s["configVersion"] == frozen
                    and s["routes"]["TRANSLATION_FULL_TEXT"]["model"]
                    == "deepseek-flash"
                    for s in snapshot
                )
                last_stage = None
                timed_out = False
                disk_stop = False
                while True:
                    current = disk()
                    append("disk-observations.jsonl", current)
                    task = api("GET", "/api/tasks/" + task_id)
                    if task.get("currentStage") != last_stage:
                        last_stage = task.get("currentStage")
                        append(
                            "progress.jsonl",
                            {"utc": utc(), "trial_id": trial_id, "task": task},
                        )
                        print(
                            json.dumps(
                                {
                                    "trial_id": trial_id,
                                    "stage": last_stage,
                                    "status": task["status"],
                                }
                            ),
                            flush=True,
                        )
                    if task["status"] in {"SUCCEEDED", "FAILED", "CANCELED"}:
                        break
                    if current["percent"] > 85 or time.monotonic() - started >= 1800:
                        disk_stop = current["percent"] > 85
                        timed_out = not disk_stop
                        cancel = api("POST", "/api/tasks/" + task_id + "/cancel")
                        save(
                            "cancellations/" + trial_id + ".json",
                            {
                                "response": cancel,
                                "reason": "DISK_ABOVE_85"
                                if disk_stop
                                else "TASK_30_MIN_LIMIT",
                                "utc": utc(),
                            },
                        )
                        break
                    time.sleep(2)
                terminal_ms = (time.monotonic() - started) * 1000
                result = api("GET", "/api/tasks/" + task_id + "/results")
                save("results/" + trial_id + ".json", result, private=True)
                final = api("GET", "/api/tasks/" + task_id)
                events = journal(created, task_id)
                save("events/" + trial_id + ".json", events)
                index = None
                if task["status"] == "SUCCEEDED":
                    while time.monotonic() - started < 1800:
                        index = api(
                            "GET", "/api/tasks/" + task_id + "/evidence/index-status"
                        )
                        if index.get("status", index.get("state")) == "READY":
                            break
                        if disk()["percent"] > 85:
                            disk_stop = True
                            break
                        time.sleep(2)
                calls = result.get("aiCallRecords") or []
                summary = {
                    "taskId": task_id,
                    "translationStatus": result.get("translationStatus"),
                    "source_characters": len(result.get("sourceFullText") or ""),
                    "source_sha256": hashlib.sha256(
                        (result.get("sourceFullText") or "").encode()
                    ).hexdigest(),
                    "source_segment_count": len(result.get("subtitles") or []),
                    "aiCallRecords": calls,
                }
                save("results/" + trial_id + ".json", summary)
                row.update(
                    {
                        "phase": "finished",
                        "finished_utc": utc(),
                        "task": final,
                        "measurement_status": "FAILED_30_MIN_LIMIT"
                        if timed_out
                        else "STOPPED_DISK"
                        if disk_stop
                        else final["status"],
                        "task_terminal_ms": terminal_ms,
                        "processing_to_index_ms": (time.monotonic() - started) * 1000,
                        "index_status": index,
                        "config_version": frozen,
                    }
                )
                append("trials.jsonl", row)
                print(
                    json.dumps(
                        {
                            "finished": trial_id,
                            "status": row["measurement_status"],
                            "elapsed_ms": row["processing_to_index_ms"],
                        }
                    ),
                    flush=True,
                )
                if disk_stop:
                    save(
                        "STOP.json",
                        {
                            "reason": "DISK_ABOVE_85",
                            "trial_id": trial_id,
                            "disk": disk(),
                        },
                    )
                    return
                if timed_out:
                    save(
                        "timeout-observation.json",
                        {
                            "trial_id": trial_id,
                            "task_id": task_id,
                            "note": "Recorded failed at 30 min; cancellation requested; no timeout extension.",
                        },
                    )
        save(
            "COMPLETE.json",
            {
                "utc": utc(),
                "finished": 10,
                "binding_retained": True,
                "config_version": frozen,
            },
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 -- persist sanitized failure and stop without replay
        save(
            "DRIVER_FAILURE.json",
            {"utc": utc(), "type": type(exc).__name__, "message": str(exc)},
        )
        raise SystemExit(
            "Measurement driver stopped; sanitized failure record saved"
        ) from None
