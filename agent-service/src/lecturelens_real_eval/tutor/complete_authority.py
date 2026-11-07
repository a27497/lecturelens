"""Negotiated bounded raw Evidence; old Java servers fail before model dispatch."""

import hashlib
import time

import httpx
from lecturelens_agent.study.authority import EvidenceAuthority, authority_path, request_body, signature
from lecturelens_agent.study.learning_scope import check_scope_response, inject_scope
from lecturelens_agent.study.store import StudyError


class CompleteEvidenceAuthority(EvidenceAuthority):
    def __init__(self, url, secret, *, transport=None):
        super().__init__(url, secret)
        self.transport = transport

    def read(self, scope, action="CHECK", **arguments):
        payload = inject_scope(
            scope,
            {
                **{k: scope[k] for k in ("owner_id", "course_id", "revision")},
                "action": action,
                **arguments,
                "text_policy": "complete-v1",
            },
        )
        path, timestamp = authority_path(payload), str(int(time.time()))
        raw = request_body(payload)
        with httpx.Client(
            timeout=10, trust_env=False, follow_redirects=False, transport=self.transport
        ) as client:
            response = client.post(
                self.url + path,
                content=raw,
                headers={
                    "Content-Type": "application/json",
                    "X-LectureLens-Timestamp": timestamp,
                    "X-LectureLens-Signature": signature(self.secret, timestamp, raw, path),
                },
            )
        if response.status_code in (401, 403, 404, 409):
            raise StudyError("COURSE_UNAVAILABLE_OR_CHANGED")
        if response.status_code == 400:
            raise StudyError("TUTOR_EVIDENCE_CAPACITY_OR_CONTRACT")
        response.raise_for_status()
        result = response.json()["data"]
        if result.get("text_policy") != "complete-v1" or any(
            result.get(k) != payload[k] for k in ("owner_id", "course_id", "revision")
        ):
            raise StudyError("EVIDENCE_SCOPE_MISMATCH")
        check_scope_response(payload, result)
        rows = result["evidence"]
        if (
            len(rows) > 8
            or sum(len(e["text"]) for e in rows) > 16000
            or sum(len(e["text"].encode()) for e in rows) > 32768
        ):
            raise StudyError("TUTOR_EVIDENCE_CAPACITY_OR_CONTRACT")
        for row in rows:
            if (
                not row.get("text_complete")
                or not row["text"].strip()
                or len(row["text"]) > 8000
                or hashlib.sha256(row["text"].encode()).hexdigest() != row.get("content_hash")
            ):
                raise StudyError("TUTOR_EVIDENCE_CAPACITY_OR_CONTRACT")
        return result
