"""Opt-in, session-scoped contract evidence for a private QA review probe.

This observation never changes validation, provider inputs, retries or public errors.
"""

import hashlib
import inspect
import json
import os
import re
from importlib.metadata import version

_MODE = "answer_support_v1"
_FIELDS = {
    "goal_checks",
    "explanation_checks",
    "id",
    "observation",
    "matches",
    "answer_quotes",
    "course_fact",
    "evidence_ids",
    "supported",
    "claim_checks",
    "answer_claim_ids",
}
_SENSITIVE = re.compile(r"api.?key|token|cookie|authorization|password|secret|credential", re.I)


def validation_diagnostics(errors):
    """Expose declared paths and numeric bounds, never model values or messages."""
    result = []
    for error in errors[:10]:
        location = error.get("loc", ())
        item = {
            "field": "issues" if location and location[0] == "issues" else "other",
            "type": error["type"],
        }
        if (
            location
            and len(location) <= 8
            and all((type(part) is int and 0 <= part <= 24) or part in _FIELDS for part in location)
        ):
            item["path"] = list(location)
            bounds = {
                key: value
                for key, value in error.get("ctx", {}).items()
                if key in {"max_length", "min_length", "actual_length"}
                and type(value) is int
                and 0 <= value <= 10000
            }
            if bounds:
                item["bounds"] = bounds
        result.append(item)
    return result


def goal_scope_detail(body, arguments, errors=()):
    """IDs, enum judgments, hashes and fixed predicates; no model/source prose."""
    from .goal_obligations import carries_obligation

    scope = body.get("goal_scope_binding", {})
    obligations = {o["id"]: o for o in scope.get("obligations", [])[:9]}
    answer = body.get("candidate", {}).get("explanation", "")
    checks = arguments.get("goal_checks", []) if isinstance(arguments, dict) else []
    observations = []
    for check in checks[:9] if isinstance(checks, list) else []:
        if not isinstance(check, dict):
            continue
        obligation = obligations.get(check.get("id")) if isinstance(check.get("id"), str) else None
        quote = check.get("answer_quote")
        exact = isinstance(quote, str) and quote in answer
        observations.append(
            {
                "obligation_id": obligation["id"] if obligation else "unoffered",
                "kind": obligation["kind"] if obligation else "unknown",
                "requirement_sha256": hashlib.sha256(obligation["text"].encode()).hexdigest()
                if obligation
                else None,
                "model_status": check.get("status")
                if check.get("status") in ("satisfied", "unsatisfied")
                else "invalid",
                "quote_length": min(len(quote), 10000) if isinstance(quote, str) else None,
                "quote_sha256": hashlib.sha256(quote.encode()).hexdigest()
                if isinstance(quote, str)
                else None,
                "quote_in_answer": exact,
                "quote_start": answer.find(quote) if exact and quote else None,
                "lexical_signal_only": carries_obligation(obligation, answer) if obligation else None,
            }
        )
    conditions = []
    for error in errors[:10]:
        ctx = error.get("ctx", {})
        rule = ctx.get("rule")
        if rule in {"exact_obligation_ids_once", "current_answer_quote"}:
            ref = ctx.get("obligation_id")
            conditions.append({"rule": rule, "obligation_id": ref if ref in obligations else None})
        elif error.get("loc", ())[:1] == ("goal_checks",):
            conditions.append({"rule": "goal_check_schema", "validation_type": error["type"]})
    return {
        "version": "safe-goal-scope-v1",
        "scope_sha256": scope.get("scope_sha256"),
        "assessments": observations,
        "validator_conditions": conditions,
        "protocol_valid": not conditions,
    }


def enabled(body):
    session = os.environ.get("AGENT_PRIVATE_REVIEW_TELEMETRY_SESSION", "")
    if (
        not session
        or not isinstance(body, dict)
        or body.get("review_mode")
        not in {
            _MODE,
            "atomic_answer_support_v1",
            "atomic_delta_support_v1",
            "atomic_answer_spans_v2",
            "atomic_delta_spans_v2",
        }
    ):
        return False
    from .telemetry import _span

    return (_span.get() or {}).get("session_id") == session


def _redactor(secrets=()):
    hidden = [value for value in secrets if isinstance(value, str) and len(value) >= 4]
    hidden += [
        value
        for name, value in os.environ.items()
        if _SENSITIVE.search(name) and len(value) >= 4 and name != "AGENT_PRIVATE_REVIEW_TELEMETRY_SESSION"
    ]

    def scrub(value):
        for secret in hidden:
            value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [REDACTED]", value)
        value = re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "[REDACTED]", value)
        return re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", value)

    return scrub


def semantic_review_detail(answer, checks, *, revision_triggered=False, secrets=()):
    """Observe the full addressed claims; a verdict remains the model's decision."""
    from .goals import explanation_claims

    scrub = _redactor(secrets)
    claims = {claim["id"]: claim["text"] for claim in explanation_claims(answer)}
    observations = []
    for check in checks[:6]:
        if not isinstance(check, dict) or not isinstance(check.get("id"), str) or check["id"] not in claims:
            continue
        refs = check.get("evidence_ids", [])
        if not isinstance(refs, list):
            refs = []
        fact = check.get("course_fact", "")
        observations.append(
            {
                "claim_id": check["id"],
                "claim_sha256": hashlib.sha256(claims[check["id"]].encode()).hexdigest(),
                "evidence_ids": [scrub(ref)[:80] for ref in refs[:8] if isinstance(ref, str)],
                "supported": check.get("supported") if type(check.get("supported")) is bool else None,
                "whole_claim_observation": scrub(fact).encode()[:480].decode(errors="ignore")
                if isinstance(fact, str)
                else "",
            }
        )
    return {"claims": observations, "revision_triggered": revision_triggered}


def atomic_review_detail(answer, checks, *, revision_triggered=False, secrets=()):
    from .atomic import atomic_claims

    scrub = _redactor(secrets)
    claims = {c["id"]: c for c in atomic_claims(answer)}
    observations = []
    for check in checks[:24]:
        if not isinstance(check, dict) or not isinstance(check.get("id"), str) or check["id"] not in claims:
            continue
        claim = claims[check["id"]]
        refs = check.get("evidence_ids", [])
        if not isinstance(refs, list):
            refs = []
        observations.append(
            {
                "claim_id": claim["id"],
                "start": claim["start"],
                "end": claim["end"],
                "claim_sha256": hashlib.sha256(claim["source_text"].encode()).hexdigest(),
                "normalized_claim_sha256": hashlib.sha256(claim["normalized_claim"].encode()).hexdigest(),
                "evidence_ids": [scrub(ref)[:80] for ref in refs[:8] if isinstance(ref, str)],
                "supported": check.get("supported") if type(check.get("supported")) is bool else None,
            }
        )
    return {"claims": observations, "revision_triggered": revision_triggered}


def contract_detail(body, calls, schema, errors=(), *, secrets=()):
    """Keep only declared review arguments, with fixed byte/node/cardinality limits."""
    if body.get("goal_scope_binding"):
        # Scoped review probes need judgments and validator predicates, never
        # a copied raw model response (even when it is declared JSON).
        from .goal_scope import ScopedGoalVerdict

        return {
            "telemetry_version": "safe-goal-scope-v1",
            "schema_sha256": hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest(),
            "validator_sha256": hashlib.sha256(inspect.getsource(ScopedGoalVerdict).encode()).hexdigest(),
            "goal_scope": goal_scope_detail(body, calls[0].get("arguments") if calls else None, errors),
        }
    scrub = _redactor(secrets)

    def name(key):
        if not isinstance(key, str) or _SENSITIVE.search(key):
            return "[REDACTED_FIELD]"
        safe = scrub(key)
        return safe if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,39}", safe) else "[UNDECLARED_FIELD]"

    budget = [8192, 128]
    types, truncated = {}, []

    def text(value, limit=1024):
        raw = scrub(value).encode()
        allowed = min(limit, max(0, budget[0]))
        budget[0] -= min(len(raw), allowed)
        return raw[:allowed].decode(errors="ignore")

    def copy(value, path="", depth=0):
        if budget[1] <= 0 or depth > 6:
            truncated.append(path[:160])
            return "[LIMIT]"
        budget[1] -= 1
        types[path[:160] or "$"] = type(value).__name__
        if isinstance(value, dict):
            result = {}
            for key, item in list(value.items())[:12]:
                label = name(key)
                child = f"{path}.{label}".lstrip(".")
                if key not in _FIELDS or label != key:
                    result[label] = "[REDACTED_UNDECLARED_FIELD]"
                    types[child[:160]] = type(item).__name__
                else:
                    result[key] = copy(item, child, depth + 1)
            if len(value) > 12:
                truncated.append(path[:160])
            return result
        if isinstance(value, list):
            if len(value) > 8:
                truncated.append(path[:160])
            return [copy(item, f"{path}[{index}]", depth + 1) for index, item in enumerate(value[:8])]
        if isinstance(value, str):
            safe = text(value)
            if len(safe.encode()) < len(scrub(value).encode()):
                truncated.append(path[:160])
            return safe
        if value is None or type(value) is bool:
            return value
        if type(value) in (int, float):
            if len(str(value)) > 64:
                truncated.append(path[:160])
                return "[NUMBER_LIMIT]"
            return value
        return "[UNSUPPORTED_TYPE]"

    def fingerprint(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    candidate_ids = body.get("candidate", {}).get("evidence_ids", [])[:8]
    observed_ids = [item.get("evidence_id") for item in body.get("evidence", [])[:8]]
    allowed = set(candidate_ids) & set(observed_ids)
    records = []
    for call in calls[:3]:
        arguments = call.get("arguments")
        records.append(
            {
                "tool_name": call.get("name")
                if call.get("name") == "assess_study_candidate"
                else "unoffered",
                "arguments": copy(arguments),
                "parsed_fields": [name(key) for key in list(arguments)[:12]]
                if isinstance(arguments, dict)
                else [],
            }
        )
    failures = []
    for error in errors[:10]:
        location = [part if isinstance(part, int) else name(part) for part in error.get("loc", ())[:8]]
        failures.append(
            {
                "path": location,
                "type": str(error.get("type", ""))[:80],
                "message": text(str(error.get("msg", "")), 512),
            }
        )
    observations = []
    # Pydantic model validators report loc=(). Explain a known binding rejection
    # using the actual arguments, retaining the original root error separately.
    arguments = calls[0].get("arguments", {}) if calls else {}
    if isinstance(arguments, dict):
        for error in errors:
            message = error.get("msg", "")
            if "Goal support must quote the actual answer" in message:
                answer = body.get("candidate", {}).get("explanation", "")
                for i, check in enumerate(arguments.get("goal_checks", [])[:6]):
                    if not isinstance(check, dict):
                        continue
                    quotes = check.get("answer_quotes", [])
                    if check.get("matches") is True and not quotes:
                        observations.append(
                            {
                                "path": ["goal_checks", i, "answer_quotes"],
                                "rule": "matches=true requires a nonempty answer quotation",
                            }
                        )
                    for j, quote in enumerate(quotes[:3]):
                        if isinstance(quote, str) and quote not in answer:
                            observations.append(
                                {
                                    "path": ["goal_checks", i, "answer_quotes", j],
                                    "rule": "not an exact substring of current candidate.explanation",
                                }
                            )
            if "Answer claims require their own observed citations" in message:
                field = (
                    "claim_checks"
                    if body.get("review_mode")
                    in {
                        "atomic_answer_support_v1",
                        "atomic_delta_support_v1",
                        "atomic_answer_spans_v2",
                        "atomic_delta_spans_v2",
                    }
                    else "explanation_checks"
                )
                for i, check in enumerate(arguments.get(field, [])[:24]):
                    if not isinstance(check, dict):
                        continue
                    seen = set()
                    for j, ref in enumerate(check.get("evidence_ids", [])[:8]):
                        if isinstance(ref, str):
                            if ref not in allowed or ref in seen:
                                observations.append(
                                    {
                                        "path": [field, i, "evidence_ids", j],
                                        "rule": "outside candidate/observed citation intersection"
                                        if ref not in allowed
                                        else "duplicate Evidence ID",
                                    }
                                )
                            seen.add(ref)
    from .answer_review import ExplanationVerdict

    validator = ExplanationVerdict
    if body.get("review_mode") in {
        "atomic_answer_support_v1",
        "atomic_delta_support_v1",
        "atomic_answer_spans_v2",
        "atomic_delta_spans_v2",
    }:
        from .quality import review_contract

        validator = review_contract(review_mode=body["review_mode"])

    detail = {
        "telemetry_version": "private-review-contract-v1",
        "expected_schema_version": body.get("review_mode", _MODE),
        "schema_sha256": fingerprint(schema),
        "validator_sha256": hashlib.sha256(inspect.getsource(validator).encode()).hexdigest(),
        "pydantic_version": version("pydantic"),
        "tool_call_count": min(len(calls), 16),
        "calls": records,
        "field_value_types": types,
        "validator_errors": failures,
        "validator_location": (
            "atomic_review.py:AtomicAnswerVerdict.bind_claims"
            if body.get("review_mode")
            in {
                "atomic_answer_support_v1",
                "atomic_delta_support_v1",
                "atomic_answer_spans_v2",
                "atomic_delta_spans_v2",
            }
            else "answer_review.py:ExplanationVerdict.bind_answer_and_sources"
        )
        if any(not error.get("loc") and error.get("type") == "value_error" for error in errors)
        else "Pydantic field validation",
        "binding_observations": observations[:12],
        "truncated_paths": truncated[:16],
        "candidate_citation_ids_sha256": fingerprint(candidate_ids),
        "observed_evidence_ids_sha256": fingerprint(observed_ids),
        "allowed_citation_ids": sorted(allowed)[:8],
        "resolved_goal_sha256": fingerprint(body.get("goal", "")),
    }
    atomic = body.get("review_mode") in {
        "atomic_answer_support_v1",
        "atomic_delta_support_v1",
        "atomic_answer_spans_v2",
        "atomic_delta_spans_v2",
    }
    checks = (
        arguments.get("claim_checks" if atomic else "explanation_checks", [])
        if isinstance(arguments, dict)
        else []
    )
    if isinstance(checks, list):
        detail["semantic_review"] = (atomic_review_detail if atomic else semantic_review_detail)(
            body.get("candidate", {}).get("explanation", ""),
            checks,
            secrets=secrets,
        )
    if len(json.dumps(detail).encode()) > 24 * 1024:
        detail["field_value_types"] = dict(list(types.items())[:32])
        detail["truncated_paths"] = ["field_value_types", *truncated[:8]]
    if len(json.dumps(detail).encode()) > 24 * 1024:
        detail["calls"] = [
            {"tool_name": record["tool_name"], "arguments": "[DETAIL_LIMIT]"} for record in records
        ]
        detail["truncated_paths"].append("arguments")
    if len(json.dumps(detail).encode()) > 24 * 1024:
        for claim in detail.get("semantic_review", {}).get("claims", []):
            claim.pop("whole_claim_observation", None)
        detail["validator_errors"] = failures[:5]
        detail["binding_observations"] = observations[:6]
        detail["truncated_paths"] = ["semantic observations", "validator_errors", *truncated[:6]]
    return detail
