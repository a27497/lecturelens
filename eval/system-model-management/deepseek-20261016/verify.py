"""Offline acceptance replay. Never contacts a provider or modifies a service/database."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

PUBLIC = Path(__file__).resolve().parent
ROOT = PUBLIC.parents[2]
RAW = ROOT / ".data/system-model-management/deepseek-20261016"


def read(name):
    return json.loads((PUBLIC / name).read_text())


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def manifest(name):
    count = 0
    for line in (PUBLIC / name).read_text().splitlines():
        expected, path = line.split("  ", 1)
        assert checksum(ROOT / path) == expected, path
        count += 1
    return count


def check_redaction(value):
    if isinstance(value, dict):
        forbidden = {"apikey", "api_key", "ciphertext", "api_key_ciphertext", "authorization", "accesstoken", "refreshtoken", "credentialid", "credentialref", "environmentfingerprint", "config_json", "configjson"}
        assert not forbidden.intersection(k.lower() for k in value)
        if "keyLast4" in value:
            assert value["keyLast4"] in (None, "****")
        for child in value.values():
            check_redaction(child)
    elif isinstance(value, list):
        for child in value:
            check_redaction(child)


def instant(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def main():
    public_files = manifest("SHA256SUMS")
    raw_files = manifest("RAW_SHA256SUMS")
    for path in PUBLIC.glob("*.json"):
        check_redaction(json.loads(path.read_text()))
        assert not re.search(r"\bsk-[A-Za-z0-9_-]{24,}", path.read_text())
    result = read("results.json")
    probe = read("json-probe.json")["response"]
    assert probe["ok"] and probe["category"] == "OK" and probe["elapsedMillis"] == 663
    assert probe["finalUrl"] == "https://api.deepseek.com/chat/completions"
    assert read("probe-policy.json")["allowedOrigins"] == ["https://api.deepseek.com"]
    baseline = read("baseline-catalog.json")
    final = read("final-catalog.json")
    assert baseline["version"] == 3 and final["version"] == 9
    assert baseline["bindings"] == final["bindings"] == {}
    assert baseline["effective"] == final["effective"]
    for filename in ("bound-catalog.json", "trial-02-bound-catalog.json", "live-bound-catalog.json"):
        bound = read(filename)
        assert bound["bindings"] == {"TRANSLATION_FULL_TEXT": 1}
        for feature, route in baseline["effective"].items():
            if feature != "TRANSLATION_FULL_TEXT":
                assert bound["effective"][feature] == route
    digests = read("immutable-content-digests.json")["versions"]
    assert [row["version"] for row in digests] == list(range(3, 10))
    for row in digests:
        for key in ("providers_sha256", "models_sha256", "deployment_defaults_sha256"):
            assert row[key] == digests[0][key]
    snapshot_a = read("live-task-a-snapshot-final.json")
    assert snapshot_a == read("live-task-a-snapshot-before-rollback.json") == read("live-task-a-snapshot-after-rollback.json")
    assert len(snapshot_a) == 1 and snapshot_a[0]["configVersion"] == 6
    assert snapshot_a[0]["routes"]["TRANSLATION_FULL_TEXT"]["source"] == "DATABASE"
    assert snapshot_a[0]["routes"]["TRANSLATION_FULL_TEXT"]["model"] == "deepseek-flash"
    snapshot_b = read("live-task-b-snapshot-final.json")
    assert len(snapshot_b) == 1 and snapshot_b[0]["configVersion"] == 9
    assert snapshot_b[0]["routes"] == baseline["effective"]
    assert snapshot_a[0]["fullTextTranslation"] and snapshot_b[0]["fullTextTranslation"]
    for row in read("database-execution-snapshots.json")["rows"]:
        assert not row["has_credential_payload"]
    timeline = read("hot-timeline.json")
    assert instant(timeline["translation_started"]) < instant(timeline["rollback_to_original_binding_at"]) < instant(timeline["translation_a_finished"])
    assert instant(timeline["task_b_created"]) > instant(timeline["rollback_to_original_binding_at"])
    assert read("task-a-running-before-final-rollback.json")["currentStage"] == "TRANSLATE_SUBTITLES"
    source_hashes = []
    for label, model in (("a", "deepseek-flash"), ("b", "lecturelens-local-qwen")):
        assert read(f"live-task-{label}-status.json")["status"] == "SUCCEEDED"
        summary = read(f"task-{label}-results.json")
        raw = json.loads((RAW / f"task-{label}-result-content.json").read_text())
        assert summary["translationStatus"] == raw["translationStatus"] == "SUCCEEDED"
        assert len(raw["sourceFullText"]) == summary["source_chars"] == 1061
        assert len(raw["translatedFullText"]) == summary["translated_chars"]
        assert hashlib.sha256(raw["sourceFullText"].encode()).hexdigest() == summary["source_sha256"]
        assert hashlib.sha256(raw["translatedFullText"].encode()).hexdigest() == summary["translation_sha256"]
        assert len(re.findall("[\u4e00-\u9fff]", raw["translatedFullText"])) == summary["chinese_chars"]
        assert summary["subtitle_segments"] == summary["translation_segments"] == 6
        assert summary["learning_package_present"]
        calls = summary["calls"]
        assert len(calls) == 3 and all(call["status"] == "SUCCEEDED" for call in calls)
        assert next(c for c in calls if c["stage"] == "TRANSCRIPTION")["provider"] == "embedded-subtitle"
        assert next(c for c in calls if c["stage"] == "TRANSLATION")["model"] == model
        assert next(c for c in calls if c["stage"] == "LEARNING_PACKAGE")["model"] == "lecturelens-local-qwen"
        source_hashes.append(summary["source_sha256"])
    assert len(set(source_hashes)) == 1
    call = next(c for c in read("task-a-results.json")["calls"] if c["stage"] == "TRANSLATION")
    assert call["batchCount"] == 6 and call["retryCount"] == 0
    assert call["promptTokens"] == 1737 and call["completionTokens"] == 2719
    assert call["totalTokens"] == 4456 == call["promptTokens"] + call["completionTokens"]
    for label in ("a", "b"):
        failed = read(f"attempt-01-task-{label}-status.json")
        assert failed["status"] == "FAILED" and failed["errorCode"] == "MQ_DELIVERY_EXHAUSTED"
    assert read("other-services-before-broker-restart.json") == read("other-services-after-broker-restart.json")
    assert read("broker-restart-before.json")["image_id"] == read("broker-restart-after.json")["image_id"]
    assert read("broker-final-protection.json") == {"diskSpaceCleanForciblyRatio": 85, "diskSpaceWarningLevelRatio": 90}
    assert result["unfinished_tasks"] == result["real_asr_requests"] == 0
    media = read("media.json")
    assert checksum(ROOT / media["clip_private_path"]) == media["clip_sha256"]
    assert checksum(RAW / "clip.vtt") == media["subtitle_sha256"]
    print(json.dumps({"accepted_tasks": 2, "failed_delivery_tasks_preserved": 2, "frozen_versions": [6, 9], "current_version": 9, "probe_elapsed_millis": 663, "deepseek_translation_batches": 6, "translation_tokens": 4456, "real_asr_calls": 0, "public_files": public_files, "private_files": raw_files}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
