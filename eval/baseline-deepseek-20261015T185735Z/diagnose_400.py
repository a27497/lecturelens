"""Offline request summaries joined to original response-only HTTP 400 capture."""

import hashlib
import json
import re
from datetime import datetime

from support import PRIVATE, PUBLIC, ROOT, save


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def main():
    events = [json.loads(x) for x in (PUBLIC / "trials.jsonl").read_text().splitlines()]
    path = PUBLIC / "local-http-400-responses.jsonl"
    responses = (
        [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
    )
    java = (
        ROOT
        / "backend/src/main/java/com/example/courselingo/learning/service/LearningPackagePromptFactory.java"
    ).read_text()
    system = (
        java.split("private static LlmMessage systemMessage()", 1)[1]
        .split('"""', 2)[1]
        .removeprefix("\n")
    )
    reports = []
    for trial in events:
        if trial["phase"] != "finished":
            continue
        result = json.loads(
            (PRIVATE / "results" / f"{trial['trial_id']}.json").read_text()
        )
        errors = [
            c
            for c in result.get("aiCallRecords", [])
            if c["stage"] == "LEARNING_PACKAGE"
            and c["status"] == "FAILED"
            and (
                "400" in (trial.get("task", {}).get("errorMessage") or "")
                or "400" in (c.get("errorMessage") or "")
                or c.get("errorCode") == "INVALID_REQUEST"
            )
        ]
        if not errors:
            continue
        source = result.get("sourceFullText") or ""
        translated = result.get("translatedFullText") or ""
        user = (
            "Build a learning package from this course transcript.\n\nSource language: en\nTarget language: zh-CN\n"
            "Target-language title is required. Quality requirements: tier=SPARSE, summary effective characters=1-300, keyPoints=1-3, glossary=0-3, qa=0-2\n\n"
            "Source transcript:\n"
            + source
            + "\n\nTranslated transcript:\n"
            + translated
            + '\n\nBounded multimodal timeline JSON (untrusted course evidence): {"mode":"TRANSCRIPT_ONLY","segments":[]}'
        )
        started = datetime.fromisoformat(trial["created_utc"]).timestamp()
        finished = datetime.fromisoformat(trial["finished_utc"]).timestamp()
        matching = [
            r for r in responses if started <= r["packet_unix_timestamp"] <= finished
        ]
        request = {
            "origin": "Reconstructed offline from immutable task result and unchanged prompt factory; not a request capture. No extra inference call.",
            "method": "POST",
            "url": "http://127.0.0.1:8091/v1/chat/completions",
            "content_type": "application/json",
            "model": "lecturelens-local-qwen",
            "temperature": 0.2,
            "max_tokens": 4096,
            "stream": False,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "characters": len(system), "sha256": digest(system)},
                {"role": "user", "characters": len(user), "sha256": digest(user)},
            ],
            "source_characters": len(source),
            "source_sha256": digest(source),
            "translated_characters": len(translated),
            "translated_sha256": digest(translated),
            "prompt_factory_sha256": digest(java),
            "headers": "Content-Type only documented; no authorization header captured or read",
            "evidence_notes": "Full-text path, no visual segments. Request factory explicitly sets temperature=0.2 and maxTokens=4096, overriding ENV defaults; JSON object format retained.",
        }
        local_logs = json.loads(
            (PRIVATE / "logs" / f"{trial['task_id']}.json").read_text()
        )
        lengths = [
            int(m.group(1))
            for line in local_logs
            if (
                m := re.search(
                    r"event=learning_package_llm_started.*inputLength=(\d+)", line
                )
            )
        ]
        reports.append(
            {
                "trial_id": trial["trial_id"],
                "task_id": trial["task_id"],
                "config_version": trial["config_version"],
                "failure_records": errors,
                "request_summary": request,
                "logged_translated_input_lengths": lengths,
                "original_http_400_responses": matching,
                "response_association": "Unique serial trial time window; server response direction captured, not request headers.",
                "diagnosis": "See original response error type/message and n_prompt_tokens/n_ctx. No repair, replay, prompt truncation or context change performed.",
            }
        )
    save("http-400-diagnostics.json", reports)
    print(
        json.dumps(
            {
                "http_400_trials": len(reports),
                "original_responses_matched": sum(
                    len(x["original_http_400_responses"]) for x in reports
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
