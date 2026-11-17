"""Send one frozen item to one product path and record the raw result privately.

Product code runs unchanged:
- rag: Java POST /api/tasks/{id}/qa (Dense retrieval in Python, one COURSE_QA call in Java).
- study: Java Study gateway CREATE_SESSION + START, then READ until the Run is terminal.
- tutor: the product Light Tutor runtime in this process (TrialTutorRuntime + FlashProvider text
  wire). Only admission is replaced: L4TutorStore reserves in the L4 ledger instead of using the
  single-trial receipt. The Java Tutor HTTP gateway and the receipt are NOT_RUN.
The harness never retries a product request. Every unit reserves its upper bound first.
"""

import json
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import psycopg
from psycopg.rows import dict_row

from .ledger import BudgetExceeded
from .pricing import upper_nano

QA_INSUFFICIENT = "当前课程内容中没有找到明确依据"
# Upper bounds (PLAN.json budget.upper_bounds_per_request_peak_usd basis).
RAG_UPPER = upper_nano("deepseek-flash", 6_000, 1_024)
STUDY_UPPER = upper_nano("deepseek-flash", 600_000, 12 * 4_096)
STUDY_POLL_SECONDS = 330  # Run deadline is 90 s from first claim; this only bounds a stuck worker.
TUTOR_POLL_SECONDS = 150  # Turn deadline is 90 s (TURN_DEADLINE_SECONDS).


def utcnow():
    return datetime.now(timezone.utc)


class Java:
    def __init__(self, base, session_path):
        self.base, self.session_path = base.rstrip("/"), Path(session_path)
        self.saved = json.loads(self.session_path.read_text())

    def login(self):
        self.saved["token"] = self.call("POST", "/api/auth/login", self.saved["credentials"], auth=False)[
            "accessToken"
        ]
        self.session_path.write_text(json.dumps(self.saved))

    def call(self, method, path, body=None, *, auth=True, retry=True, timeout=120):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = "Bearer " + self.saved["token"]
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())["data"]
        except urllib.error.HTTPError as error:
            if error.code == 401 and auth and retry:
                self.login()
                return self.call(method, path, body, auth=auth, retry=False, timeout=timeout)
            payload = error.read()[:2000]
            try:
                code = json.loads(payload).get("code")
            except ValueError:
                code = None
            raise ProductError(f"HTTP_{error.code}", code) from None

    def me(self):
        return self.call("GET", "/api/me")

    def evidence(self, task):
        items, after = [], ""
        while True:
            page = self.call("GET", f"/api/tasks/{task}/evidence?limit=200&after={after}")
            items += page["items"]
            after = page.get("nextCursor")
            if not after:
                return items


class ProductError(RuntimeError):
    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code, self.detail = code, detail


def result(path, item, rep, **fields):
    return {
        "path": path,
        "item_id": item["item_id"],
        "lecture_id": item["lecture_id"],
        "rep": rep,
        "recorded_at": utcnow().isoformat(),
        **fields,
    }


def run_rag(java, ledger, phase, item, rep, task):
    reservation = ledger.reserve(
        phase=phase, arm="rag", unit=f"{item['item_id']}#{rep}", model="deepseek-flash", upper_nano=RAG_UPPER
    )
    started = time.monotonic()
    sent_at = utcnow()
    try:
        response = java.call("POST", f"/api/tasks/{task}/qa", {"question": item["question"]}, timeout=120)
    except ProductError as error:
        ledger.uncertain(reservation, error.code)
        return result(
            "rag",
            item,
            rep,
            status="failed",
            error_code=error.code,
            error_detail=error.detail,
            latency_ms=round((time.monotonic() - started) * 1000),
            reservation=reservation,
        )
    latency = round((time.monotonic() - started) * 1000)
    usage = response.get("usage")
    cited = [e["evidenceId"] for e in response.get("evidence") or []]
    abstained = response.get("answer", "").strip() == QA_INSUFFICIENT or not cited
    if usage:
        calls = [
            {
                "model": "deepseek-flash",
                "at": sent_at.isoformat(),
                "usage": {
                    "prompt_tokens": usage.get("promptTokens"),
                    "completion_tokens": usage.get("completionTokens"),
                },
            }
        ]
        cost = ledger.settle(reservation, calls)
    elif abstained and not cited:
        # SKIPPED_NO_EVIDENCE: Java answered without dispatching a model call.
        ledger.release(reservation, "QA_SKIPPED_NO_EVIDENCE")
        cost, calls = 0, []
    else:
        cost, calls = ledger.uncertain(reservation, "QA_USAGE_MISSING"), []
    return result(
        "rag",
        item,
        rep,
        status="ok",
        abstained=abstained,
        text=response.get("answer", ""),
        cited=cited,
        latency_ms=latency,
        cost_nano=cost,
        calls=calls,
        raw=response,
        reservation=reservation,
    )


def study_usage(dsn, run_id):
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        events = conn.execute(
            "SELECT event_type,payload,created_at FROM study_event WHERE run_id=%s ORDER BY sequence",
            (run_id,),
        ).fetchall()
        row = conn.execute(
            "SELECT created_at,finished_at,model_calls,tool_calls,status FROM study_run WHERE run_id=%s",
            (run_id,),
        ).fetchone()
    started = sum(e["event_type"] == "model_started" for e in events)
    calls = [
        {
            "model": "deepseek-flash",
            "at": e["created_at"].isoformat(),
            "usage": (e["payload"] or {}).get("usage"),
        }
        for e in events
        if e["event_type"] in ("model_finished", "model_failed")
    ]
    return row, calls, started, events


def run_study(java, ledger, phase, item, rep, task, dsn):
    reservation = ledger.reserve(
        phase=phase,
        arm="study",
        unit=f"{item['item_id']}#{rep}",
        model="deepseek-flash",
        upper_nano=STUDY_UPPER,
    )
    endpoint = f"/api/tasks/{task}/study/command"
    key = f"l4:{phase}:{item['item_id']}:{rep}:{uuid.uuid4().hex[:8]}"
    started = time.monotonic()
    try:
        session = java.call("POST", endpoint, {"operation": "CREATE_SESSION", "request_key": key})[
            "session_id"
        ]
        state = java.call(
            "POST",
            endpoint,
            {"operation": "START", "session_id": session, "request_key": key, "goal": item["question"]},
        )
    except ProductError as error:
        ledger.uncertain(reservation, error.code)
        return result(
            "study",
            item,
            rep,
            status="failed",
            error_code=error.code,
            error_detail=error.detail,
            latency_ms=round((time.monotonic() - started) * 1000),
            reservation=reservation,
        )
    run_id = state["run"]["run_id"]
    while state["run"]["status"] in ("queued", "running"):
        if time.monotonic() - started > STUDY_POLL_SECONDS:
            ledger.uncertain(reservation, "STUDY_WORKER_STUCK")
            return result(
                "study",
                item,
                rep,
                status="failed",
                error_code="HARNESS_POLL_TIMEOUT",
                run_id=run_id,
                latency_ms=None,
                reservation=reservation,
            )
        time.sleep(0.5)
        state = java.call("POST", endpoint, {"operation": "READ", "session_id": session, "run_id": run_id})
    observed = round((time.monotonic() - started) * 1000)
    row, calls, model_started, events = study_usage(dsn, run_id)
    if len(calls) == model_started and all(c["usage"] for c in calls):
        cost = ledger.settle(reservation, calls)
    else:
        cost = ledger.uncertain(reservation, "STUDY_USAGE_INCOMPLETE", calls)
    latency = (
        round((row["finished_at"] - row["created_at"]).total_seconds() * 1000) if row["finished_at"] else None
    )
    artifact = state.get("artifact")
    succeeded = state["run"]["status"] == "succeeded" and artifact is not None
    return result(
        "study",
        item,
        rep,
        status="ok" if succeeded else "failed",
        error_code=None if succeeded else state["run"].get("error_code"),
        abstained=bool(artifact) and artifact.get("kind") == "insufficient_evidence",
        artifact=artifact,
        run=state["run"],
        run_id=run_id,
        session_id=session,
        latency_ms=latency,
        observed_ms=observed,
        cost_nano=cost,
        calls=calls,
        model_calls=row["model_calls"],
        tool_calls=row["tool_calls"],
        events=[{"type": e["event_type"], "at": e["created_at"].isoformat()} for e in events],
        reservation=reservation,
    )


class L4TutorStore:
    """Mixin replacing the trial receipt with the L4 ledger. Combined with TutorStore at runtime."""

    def setup_l4(self, ledger, offline=False):
        self.ledger = ledger
        self.grant = SimpleNamespace(
            mode="offline-fake" if offline else "real", expires_at=utcnow() + timedelta(hours=12)
        )
        self.l4_unit = None
        self.l4_reservations = {}

    def authorize_command(self, command):
        pass

    def reserve(self, conn, session, turn, state, request_sha256):
        unit = self.l4_unit or turn["turn_id"]
        upper = upper_nano("deepseek-flash", state["reservation"], 4_096)
        try:
            self.l4_reservations[turn["turn_id"]] = self.ledger.reserve(
                phase=unit[0], arm="tutor", unit=unit[1], model="deepseek-flash", upper_nano=upper
            )
        except BudgetExceeded as error:
            from lecturelens_agent.study.store import StudyError

            raise StudyError("L4_BUDGET_" + str(error), 403) from None

    def settle(self, turn_id, request_sha256, provider_result):
        reservation = self.l4_reservations.get(turn_id)
        if reservation is not None:
            if provider_result.usage:
                self.ledger.settle(
                    reservation,
                    [{"model": "deepseek-flash", "at": utcnow().isoformat(), "usage": provider_result.usage}],
                )
            else:
                self.ledger.uncertain(reservation, provider_result.error or "TUTOR_USAGE_MISSING")
        return provider_result.error

    def published(self, conn, turn_id):
        pass


def tutor_runtime(dsn, java_base, secret, api_key, ledger, *, transport=None):
    from lecturelens_agent.study.authority import EvidenceAuthority
    from lecturelens_real_eval.tutor.flash_provider import FlashProvider
    from lecturelens_real_eval.tutor.store import TutorStore
    from lecturelens_real_eval.tutor.trial import TrialTutorRuntime

    class Store(L4TutorStore, TutorStore):
        pass

    store = Store(dsn, engine="light", experiment="l4-benchmark")
    store.setup_l4(ledger, offline=transport is not None)
    provider = FlashProvider(
        "synthetic-l4-fixture" if transport is not None else api_key, transport=transport, text_reply=True
    )
    runtime = TrialTutorRuntime(store, EvidenceAuthority(java_base, secret), provider)
    runtime.initialize()
    runtime.start()
    return runtime


def run_tutor(runtime, phase, item, rep, scope):
    from lecturelens_real_eval.tutor.contracts import Command

    key = f"l4-{item['item_id']}-{rep}-{uuid.uuid4().hex[:8]}"
    runtime.store.l4_unit = (phase, f"{item['item_id']}#{rep}")
    started = time.monotonic()
    try:
        created = runtime.command(Command(**scope, operation="CREATE", request_key=key))
        session = created["session"]["session_id"]
        state = runtime.command(
            Command(
                **scope,
                operation="TURN",
                session_id=session,
                client_turn_id=key,
                text=item["question"],
                socratic=False,
            )
        )
        while True:
            turn = state["turns"][-1]
            if turn["status"] not in ("queued", "running"):
                break
            if time.monotonic() - started > TUTOR_POLL_SECONDS:
                return result(
                    "tutor", item, rep, status="failed", error_code="HARNESS_POLL_TIMEOUT", latency_ms=None
                )
            time.sleep(0.25)
            state = runtime.command(Command(**scope, operation="GET", session_id=session))
    except Exception as error:  # noqa: BLE001 -- a product refusal is a recorded failure, not a harness crash
        return result(
            "tutor",
            item,
            rep,
            status="failed",
            error_code=getattr(error, "code", type(error).__name__),
            latency_ms=round((time.monotonic() - started) * 1000),
        )
    reservation = runtime.store.l4_reservations.get(turn["turn_id"])
    ledger = runtime.store.ledger
    unit = ledger.state(ledger.events()).get(reservation) if reservation else None
    if unit is not None and unit["status"] == "reserved":
        # The turn ended without a settlement (deadline, cancellation, crash): the call may have been billed.
        ledger.uncertain(reservation, "TUTOR_TURN_" + turn["status"].upper())
        unit = ledger.state(ledger.events())[reservation]
    latency = (
        round((turn["finished_at"] - turn["created_at"]).total_seconds() * 1000)
        if turn.get("finished_at") and turn.get("created_at")
        else None
    )
    ok = turn["status"] == "completed"
    return result(
        "tutor",
        item,
        rep,
        status="ok" if ok else "failed",
        error_code=None if ok else turn.get("error_code"),
        abstained=ok and turn.get("outcome") == "insufficient_evidence",
        text=turn.get("answer") or "",
        cited=[c["evidence_id"] for c in turn.get("citations") or []],
        latency_ms=latency,
        observed_ms=round((time.monotonic() - started) * 1000),
        # No reservation means the product published its fixed abstention without a model call.
        cost_nano=0 if unit is None else unit["cost_nano"],
        calls=[] if unit is None else unit.get("calls", []),
        usage=turn.get("usage"),
        turn={
            k: (v.isoformat() if isinstance(v, datetime) else v)
            for k, v in turn.items()
            if k not in ("citations",)
        },
        reservation=reservation,
    )
