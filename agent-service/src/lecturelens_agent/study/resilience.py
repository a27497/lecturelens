"""Bounded read recovery in the Agent runtime, backed by the existing Run journal.

Every physical retry keeps Java as the authority; successful observations are
never substituted from a local cache. Artifact writes do not enter this policy.
"""

import hashlib
import json
import uuid

import httpx
from pydantic import ValidationError

from .failures import failure_category
from .learning_scope import check_scope_response, inject_scope, validate_scope_call
from .store import BudgetExceeded, RunStopped, StudyError


def execute_read(read_once, span, scope, action="CHECK", **arguments):
    from ..course_mcp.contracts import ACTION_TO_TOOL, TOOLS, CourseResult

    try:
        validate_scope_call(scope, action, arguments)
        if action not in ACTION_TO_TOOL:
            raise StudyError("MCP_INVALID_REQUEST", 422)
        _, schema, _ = TOOLS[ACTION_TO_TOOL[action]]
        schema.model_validate(
            {
                **{k: scope[k] for k in ("owner_id", "course_id", "revision")},
                **arguments,
                "authorization": {"timestamp": "0", "signature": "0" * 64},
            }
        )
        if set(arguments) & {
            "owner_id",
            "course_id",
            "revision",
            "authorization",
            "action",
            "learning_scope",
        }:
            raise StudyError("MCP_INVALID_REQUEST", 422)
    except (ValidationError, KeyError):
        public_failure(span, action, "MCP_INVALID_REQUEST", "tool_rejected")
        raise StudyError("MCP_INVALID_REQUEST", 422) from None
    except StudyError as error:
        public_failure(span, action, error.code, "tool_rejected")
        raise
    if span is None:
        result = read_once(scope, action, **arguments)
        check_scope_response(inject_scope(scope, {}), result)
        return result

    store, run_id, token = (span[k] for k in ("store", "run_id", "token"))
    ordinal = span["read_ordinal"]
    span["read_ordinal"] += 1
    key = hashlib.sha256(
        json.dumps(
            [span["node"], span["call_id"], span.get("turn"), ordinal, action, arguments], sort_keys=True
        ).encode()
    ).hexdigest()
    last_code = None
    while True:
        guard(span)
        try:
            attempt, previous_code = store.reserve_read_attempt(
                run_id,
                token,
                key,
                {
                    "action": action,
                    "call_id": span["call_id"],
                    "node": span["node"],
                    "error_code": last_code,
                    "failure_category": failure_category(last_code) if last_code else None,
                },
            )
            last_code = previous_code or last_code
            if attempt > 1 and not last_code:
                last_code = "READ_CHECKPOINT_REPLAY"
        except StudyError as error:
            public_failure(span, action, error.code, "dependency_stopped", operation_key=key)
            raise StudyError(error.code, 503) from None
        if attempt > 1:
            delay = 0.05 * 2 ** (attempt - 2)
            store.event(
                run_id,
                token,
                "tool_retry_backoff",
                {
                    "operation_key": key,
                    "action": action,
                    "attempt": attempt,
                    "delay_ms": delay * 1000,
                    "error_code": last_code,
                    "failure_category": failure_category(last_code),
                },
            )
            if span["stop"].wait(delay):
                raise RunStopped()
            guard(span)
        try:
            result = read_once(scope, action, **arguments)
            guard(span)
            check_scope_response(inject_scope(scope, {}), result)
            try:
                CourseResult.model_validate(result)
            except ValidationError:
                raise StudyError("MCP_MALFORMED_RESPONSE", 503) from None
            if any(result[k] != scope[k] for k in ("owner_id", "course_id", "revision")):
                raise StudyError("EVIDENCE_SCOPE_MISMATCH")
            store.event(
                run_id,
                token,
                "read_attempt_succeeded",
                {
                    "operation_key": key,
                    "attempt": attempt,
                    "completion_id": str(uuid.uuid4()),
                },
            )
            return result
        except (RunStopped, BudgetExceeded):
            raise
        except (
            StudyError,
            httpx.HTTPError,
            TimeoutError,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
        ) as error:
            guard(span)
            if isinstance(error, StudyError):
                code = error.code
            elif isinstance(error, (httpx.TimeoutException, TimeoutError)):
                code = "MCP_AUTHORITY_TIMEOUT"
            elif isinstance(error, httpx.HTTPError):
                code = "MCP_AUTHORITY_UNAVAILABLE"
            else:
                code = "MCP_MALFORMED_RESPONSE"
            retryable = code in {
                "MCP_TIMEOUT",
                "MCP_SERVER_UNAVAILABLE",
                "MCP_AUTHORITY_TIMEOUT",
                "MCP_AUTHORITY_UNAVAILABLE",
            }
            public_failure(span, action, code, "tool_read_failed", attempt=attempt, operation_key=key)
            if not retryable or attempt >= 3:
                public_failure(
                    span,
                    action,
                    code,
                    "dependency_stopped",
                    policy="fail_closed",
                    attempt=attempt,
                    operation_key=key,
                )
                raise StudyError(code, 503) from None
            last_code = code


def guard(span):
    if span["stop"].is_set():
        raise RunStopped()
    span["store"].guard(span["run_id"], span["token"])


def public_failure(span, action, code, event, **extra):
    if span:
        span["store"].event(
            span["run_id"],
            span["token"],
            event,
            {
                "action": action,
                "call_id": span["call_id"],
                "node": span["node"],
                "error_code": code,
                "failure_category": failure_category(code),
                **extra,
            },
        )
