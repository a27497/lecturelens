"""Closed-loop HTTP load and explicit logical-operation accounting (no retries)."""

import asyncio
import hashlib
import hmac
import ipaddress
import json
import math
import time
import uuid
from collections import Counter
from urllib.parse import urlparse

import httpx

QUESTION = "Explain the asynchronous course video learning pipeline."
TERMINAL = {"completed", "failed", "cancelled"}


def loopback(url):
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.username or parsed.password:
        raise ValueError("Only credential-free loopback HTTP origins are allowed")
    if not parsed.hostname or not ipaddress.ip_address(parsed.hostname).is_loopback:
        raise ValueError("Only literal loopback addresses are allowed")
    if parsed.path or parsed.query or parsed.fragment:
        raise ValueError("Expected an origin without a path/query/fragment")
    return url


def signed_headers(secret, body):
    timestamp = str(int(time.time()))
    message = (
        "lecturelens-retrieval-v1\nPOST\n/internal/v1/retrieve\n"
        + timestamp
        + "\n"
        + hashlib.sha256(body).hexdigest()
    )
    return {
        "Content-Type": "application/json",
        "X-LectureLens-Timestamp": timestamp,
        "X-LectureLens-Signature": hmac.new(
            secret.encode(), message.encode(), hashlib.sha256
        ).hexdigest(),
    }


def percentile(values, percent):
    """Nearest rank, including the maximum for small-sample P95."""
    return (
        round(sorted(values)[max(0, math.ceil(len(values) * percent / 100) - 1)], 3)
        if values
        else None
    )


def summary(rows, seconds):
    good = [r for r in rows if r["ok"]]
    bad = [r for r in rows if not r["ok"]]
    latencies = {}
    for name, values in (("all", rows), ("success", good), ("failure", bad)):
        ms = [r["latency_ms"] for r in values]
        latencies[name] = {"p50": percentile(ms, 50), "p95": percentile(ms, 95)}
    return {
        "attempted": len(rows),
        "succeeded": len(good),
        "failed": len(bad),
        "error_rate": len(bad) / len(rows) if rows else None,
        "wall_seconds": round(seconds, 6),
        "attempted_per_second": len(rows) / seconds if seconds > 0 else None,
        "successful_per_second": len(good) / seconds if seconds > 0 else None,
        "latency_ms": latencies,
        "http_status_counts": dict(Counter(str(r.get("http_status")) for r in rows)),
        "error_counts": dict(Counter(r["error"] for r in bad)),
        "retrieval_busy_503": sum(r.get("error") == "RETRIEVAL_BUSY_503" for r in rows),
        "retry_after_counts": dict(
            Counter(r["retry_after"] for r in rows if r.get("retry_after"))
        ),
    }


class OperationError(Exception):
    pass


class Paths:
    def __init__(
        self,
        java,
        agent,
        token,
        secret,
        owner,
        course,
        revision,
        evidence_ids,
        poll_seconds=0.1,
    ):
        self.java, self.agent = loopback(java), loopback(agent)
        self.token, self.secret = token, secret
        self.owner, self.course, self.revision = owner, course, revision
        self.evidence_ids = evidence_ids
        self.poll_seconds = poll_seconds

    async def java_api(self, client, row, method, path, body=None):
        response = await client.request(
            method,
            self.java + path,
            json=body,
            headers={"Authorization": "Bearer " + self.token},
        )
        row["http_requests"] += 1
        row["http_status"] = response.status_code
        row["retry_after"] = response.headers.get("Retry-After")
        try:
            payload = response.json()
        except ValueError:
            raise OperationError("NON_JSON_RESPONSE") from None
        if response.status_code != 200 or str(payload.get("code")) != "0":
            # Only protocol codes, never response text or credentials, enter raw output.
            code = str(payload.get("code", "UNKNOWN"))[:80]
            raise OperationError(f"JAVA_HTTP_{response.status_code}_CODE_{code}")
        return payload["data"]

    async def run(self, scenario, client, row):
        if scenario == "S1":
            await self.retrieve(client, row)
        elif scenario == "S2":
            result = await self.java_api(
                client,
                row,
                "POST",
                f"/api/tasks/{self.course}/qa",
                {"question": QUESTION},
            )
            if not result.get("answer") or not result.get("evidence"):
                raise OperationError("QA_MISSING_ANSWER_OR_EVIDENCE")
        elif scenario == "S3":
            await self.tutor(client, row)
        else:
            raise ValueError("Unknown scenario")

    async def retrieve(self, client, row):
        body = json.dumps(
            {
                "request_id": row["request_id"],
                "owner_id": self.owner,
                "course_id": self.course,
                "revision": self.revision,
                "query": QUESTION,
                "allowed_evidence_ids": self.evidence_ids,
                "top_k": 8,
            },
            separators=(",", ":"),
        ).encode()
        response = await client.post(
            self.agent + "/internal/v1/retrieve",
            content=body,
            headers=signed_headers(self.secret, body),
        )
        row["http_requests"] += 1
        row["http_status"] = response.status_code
        row["retry_after"] = response.headers.get("Retry-After")
        payload = response.json()
        if response.status_code == 503 and payload.get("detail") == "Retrieval busy":
            raise OperationError("RETRIEVAL_BUSY_503")
        if response.status_code != 200:
            raise OperationError(f"RETRIEVAL_HTTP_{response.status_code}")
        if (
            payload.get("owner_id") != self.owner
            or payload.get("course_id") != self.course
            or payload.get("revision") != self.revision
            or not payload.get("hits")
            or any(h["evidence_id"] not in self.evidence_ids for h in payload["hits"])
        ):
            raise OperationError("RETRIEVAL_INVALID_RESULT")

    async def tutor(self, client, row):
        base = f"/api/tasks/{self.course}/tutor/sessions"
        path = None
        terminal = False
        turn_key = row["request_id"]
        try:
            created = await self.java_api(
                client, row, "POST", base, {"request_key": turn_key}
            )
            path = base + "/" + created["session"]["session_id"]
            row["session_id"] = created["session"]["session_id"]
            await self.java_api(
                client,
                row,
                "POST",
                path + "/turns",
                {"client_turn_id": turn_key, "text": QUESTION, "socratic": False},
            )
            while True:
                data = await self.java_api(client, row, "GET", path)
                row["polls"] += 1
                turn = next(
                    (t for t in data["turns"] if t["client_turn_id"] == turn_key), None
                )
                if turn and turn["status"] in TERMINAL:
                    terminal = True
                    row["turn_status"] = turn["status"]
                    row["model_calls"] = turn["model_calls"]
                    if turn["status"] != "completed":
                        raise OperationError(
                            "TUTOR_" + str(turn.get("error_code") or turn["status"])
                        )
                    if (
                        turn.get("outcome") != "answered"
                        or not turn.get("citations")
                        or not turn.get("answer")
                    ):
                        raise OperationError("TUTOR_MISSING_SUPPORTED_ANSWER")
                    return
                await asyncio.sleep(self.poll_seconds)
        finally:
            if path and not terminal:
                # Drain failed/timed-out own work before another group; never leave hidden backlog.
                try:
                    cleanup_row = {"http_requests": 0}
                    async with asyncio.timeout(8):
                        await self.java_api(
                            client,
                            cleanup_row,
                            "POST",
                            path + f"/turns/{turn_key}/cancel",
                        )
                        while True:
                            data = await self.java_api(client, cleanup_row, "GET", path)
                            turns = [
                                t
                                for t in data["turns"]
                                if t["client_turn_id"] == turn_key
                            ]
                            if not turns or turns[0]["status"] in TERMINAL:
                                break
                            await asyncio.sleep(self.poll_seconds)
                    row["cleanup_ok"] = True
                except (Exception, asyncio.CancelledError):  # noqa: BLE001 -- failed drain must be recorded
                    row["cleanup_ok"] = False
                row["cleanup_http_requests"] = cleanup_row["http_requests"]


async def group(
    paths,
    scenario,
    concurrency,
    *,
    requests=None,
    seconds=None,
    timeout=60,
    raw=None,
    warmup=False,
    provenance=None,
):
    if concurrency < 1 or (requests is None) == (seconds is None):
        raise ValueError("Set positive concurrency and exactly one stopping condition")
    if requests is not None and requests < 1 or seconds is not None and seconds <= 0:
        raise ValueError("Stopping condition must be positive")
    rows = []
    allocated = 0
    wall_started = time.perf_counter()
    async with httpx.AsyncClient(
        trust_env=False,
        timeout=timeout,
        follow_redirects=False,
        limits=httpx.Limits(
            max_connections=concurrency * 2, max_keepalive_connections=concurrency
        ),
    ) as client:
        started = time.perf_counter()

        async def worker(worker_id):
            nonlocal allocated
            while True:
                if requests is not None and allocated >= requests:
                    return
                if seconds is not None and time.perf_counter() - started >= seconds:
                    return
                allocated += 1
                row = {
                    **(provenance or {}),
                    "scenario": scenario,
                    "concurrency": concurrency,
                    "warmup": warmup,
                    "worker": worker_id,
                    "request_id": uuid.uuid4().hex,
                    "ok": False,
                    "http_requests": 0,
                    "polls": 0,
                }
                before = time.perf_counter()
                try:
                    async with asyncio.timeout(timeout):
                        await paths.run(scenario, client, row)
                    row["ok"] = True
                except OperationError as error:
                    row["error"] = str(error)
                except (TimeoutError, httpx.TimeoutException):
                    row["error"] = "TIMEOUT"
                except Exception as error:  # noqa: BLE001 -- retain one failed sample without payloads
                    row["error"] = type(error).__name__
                row["latency_ms"] = round((time.perf_counter() - before) * 1000, 3)
                rows.append(row)
                if raw:
                    raw.write(json.dumps(row, sort_keys=True) + "\n")
                    raw.flush()

        await asyncio.gather(*(worker(i) for i in range(concurrency)))
    result = {"scenario": scenario, "concurrency": concurrency, "warmup": warmup}
    result.update(summary(rows, time.perf_counter() - wall_started))
    result["stop"] = {
        "requests": requests,
        "admission_seconds": seconds,
        "timeout_seconds": timeout,
    }
    result["undrained_tutor"] = any(r.get("cleanup_ok") is False for r in rows)
    return result
