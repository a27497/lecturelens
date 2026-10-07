"""Run-local identity of fenced observations, independent of retrieval order."""

import hashlib
import json


def evidence_fingerprint(scope, evidence):
    sources = [
        {
            key: item.get(key)
            for key in (
                "evidence_id",
                "start_ms",
                "end_ms",
                "source_type",
                "text",
                "text_start",
                "text_end",
                "match_start",
                "match_end",
            )
        }
        for item in evidence
    ]
    value = [
        {key: scope[key] for key in ("owner_id", "course_id", "revision")},
        sorted(sources, key=lambda item: item["evidence_id"]),
    ]
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def coverage_fingerprint(scope, semantic, evidence, practice_kind):
    value = [semantic, practice_kind, evidence_fingerprint(scope, evidence)]
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def observed_coverage(history, fingerprint):
    for entry in reversed(history):
        result = entry["result"]
        if result.get("coverage_input_fingerprint") == fingerprint and "course_coverage" in result:
            return result["course_coverage"]
    return None
