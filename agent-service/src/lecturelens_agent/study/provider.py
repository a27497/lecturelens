"""Explicit mock mode or a real chat-completions provider with standard tool calls."""

import json
import logging
import os
import re
import time
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from .context import has_time_request
from .contracts import TOOLS, tool_schemas
from .quality import AbstentionVerdict, repair_review, review_contract, review_schema, review_wire_messages
from .store import BudgetExceeded, StudyError


def bailian_nonthinking(url, model):
    """Only apply the verified Qwen profile to Alibaba's own compatible endpoints.

    Thinking-only and unknown model families keep the generic provider contract.
    See https://help.aliyun.com/zh/model-studio/qwen-function-calling.
    """
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    official = host in {
        "dashscope.aliyuncs.com",
        "dashscope-intl.aliyuncs.com",
        "dashscope-us.aliyuncs.com",
        "cn-hongkong.dashscope.aliyuncs.com",
    } or bool(
        re.fullmatch(
            r"[a-zA-Z0-9-]+\.(?:cn-beijing|cn-hongkong|ap-southeast-1|us-east-1)\.maas\.aliyuncs\.com", host
        )
    )
    return (
        parsed.scheme == "https"
        and official
        and parsed.path.rstrip("/") == "/compatible-mode/v1"
        and bool(
            re.fullmatch(
                r"(?:qwen-(?:plus|flash|turbo)|qwen3-max|qwen3\.8-(?:flash|max|27b))(?:-(?:latest|\d{4}|\d{4}-\d{2}-\d{2}))?",
                model,
            )
        )
    )


class ModelResponseError(StudyError):
    """Only bounded codes and usage may cross the runtime event boundary."""

    def __init__(self, code, usage=None, diagnostics=None):
        super().__init__(code)
        self.usage = usage or {}
        self.diagnostics = diagnostics or {}


def safe_usage(response):
    usage = response.get("usage") if isinstance(response, dict) else None
    return {
        key: value
        for key, value in (usage if isinstance(usage, dict) else {}).items()
        if key in {"prompt_tokens", "completion_tokens"} and type(value) is int and 0 <= value < 100_000_000
    }


def tool_arguments(raw):
    """Decode JSON, allowing two logged transport defects without inventing values.

    Never repair a truncated string/value, missing nested delimiter, or missing field.
    The ordinary tool schema and independent content review remain mandatory.
    """
    try:
        return json.loads(raw), []
    except (ValueError, TypeError):
        if not isinstance(raw, str):
            raise
    cleaned, stack, quoted, repairs = [], [], False, []
    index = 0
    while index < len(raw):
        char = raw[index]
        if quoted and char == "\\" and index + 1 < len(raw):
            following = raw[index + 1]
            if following == "'":
                cleaned.append("'")
                if "apostrophe_escape" not in repairs:
                    repairs.append("apostrophe_escape")
            else:
                cleaned.extend((char, following))
            index += 2
            continue
        if char == '"':
            quoted = not quoted
        elif not quoted:
            if char in "{[":
                stack.append(char)
            elif char in "}]":
                if not stack or stack.pop() != {"}": "{", "]": "["}[char]:
                    raise ValueError("Mismatched JSON delimiter")
        cleaned.append(char)
        index += 1
    value = "".join(cleaned)
    if not quoted and stack == ["{"] and value.rstrip().endswith(("}", "]")):
        value += "}"
        repairs.append("root_object_close")
    if not repairs:
        raise ValueError("Invalid tool JSON")
    return json.loads(value), repairs


def decision_schemas(messages):
    first_user = next(
        (message.get("content", "") for message in messages if message.get("role") == "user"), ""
    )
    try:
        goal = json.loads(first_user).get("goal", "")
    except (ValueError, AttributeError, TypeError):
        goal = ""
    schemas = tool_schemas(include_time_window=has_time_request(goal))
    from .goals import missing_explicit_correction_task

    if missing_explicit_correction_task(goal, ""):
        search = next(tool for tool in schemas if tool["function"]["name"] == "search_course_evidence")
        search["function"]["parameters"]["properties"]["linear_request"]["properties"]["task"]["enum"] = [
            "correct"
        ]
    if not any(message.get("role") == "tool" for message in messages):
        schemas = [tool for tool in schemas if tool["function"]["name"] == "search_course_evidence"]
    else:
        latest = next(message for message in reversed(messages) if message.get("role") == "tool")
        try:
            context = json.loads(latest["content"])
            kind = context.get("practice_kind", "auto")
        except (ValueError, TypeError, AttributeError, KeyError):
            kind = "auto"
            context = {}
        if kind == "search_cost":
            schemas = tool_schemas(include_time_window=has_time_request(goal), cost_mode=True)
        if kind == "python_strings":
            schemas = tool_schemas(include_time_window=has_time_request(goal), string_mode=True)
        modes = {
            "general": "create_practice_set",
            "linear_points": "create_linear_practice",
            "python_output": "create_python_practice",
            "python_strings_or_code": "create_python_practice",
            "python_strings": "create_python_practice",
            "interval_halving": "create_interval_practice",
            "selection_steps": "create_sequence_practice",
            "search_cost": "create_practice_set",
        }
        if kind in modes:
            schemas = [
                tool
                for tool in schemas
                if tool["function"]["name"] not in modes.values() or tool["function"]["name"] == modes[kind]
            ]
        else:
            # Old persisted decisions predate this subject choice.
            schemas = [
                tool
                for tool in schemas
                if tool["function"]["name"] not in {"create_sequence_practice", "create_linear_practice"}
            ]
        if kind == "python_strings":
            # The creation tool already computes its bounded program. A separate
            # speculative check consumes a decision without advancing this flow.
            schemas = [tool for tool in schemas if tool["function"]["name"] != "check_python_example"]
        if kind == "linear_points":
            for tool in schemas:
                if tool["function"]["name"] == "create_linear_practice":
                    point_schema = tool["function"]["parameters"]["$defs"]["PointProblem"]
                    if "construct_points" not in point_schema["required"]:
                        point_schema["required"].append("construct_points")
        if kind == "auto":
            # Legacy checkpoints cannot call the new linear tool. Avoid charging
            # its unused planning schema to every legacy repair decision.
            for tool in schemas:
                if tool["function"]["name"] == "search_course_evidence":
                    tool["function"]["parameters"]["properties"].pop("linear_request", None)
        methods = (
            context.get("course_coverage", {}).get("methods")
            if kind in {"general", "linear_points"}
            else None
        )
        for tool in schemas:
            if tool["function"]["name"] in {"create_practice_set", "create_linear_practice"}:
                params = tool["function"]["parameters"]
                if methods:
                    params["properties"]["method_id"] = {
                        "type": "string",
                        "enum": list(methods),
                        "description": "Choose the observed method for the APPLICATION operation, not the explanation/concept topic. Keep its operation/output; repeat it on new inputs or correct an execution.",
                    }

                    if "method_id" not in params["required"]:
                        params["required"].append("method_id")
                else:
                    params["properties"].pop("method_id", None)
        if methods == {} or (kind == "linear_points" and methods is None):
            schemas = [
                t
                for t in schemas
                if t["function"]["name"] not in {"create_practice_set", "create_linear_practice"}
            ]

        plan = context.get("linear_request") if kind == "linear_points" else None
        if plan:
            schemas = [tool for tool in schemas if tool["function"]["name"] != "search_course_evidence"]
            for tool in schemas:
                if tool["function"]["name"] == "create_linear_practice":
                    defs = tool["function"]["parameters"]["$defs"]
                    app = defs["PointProblem"]
                    for key in ("task", "construct_points"):
                        app["properties"].pop(key)
                        if key in app["required"]:
                            app["required"].remove(key)
                    app["properties"]["equations"].update(
                        minItems=plan["equation_count"], maxItems=plan["equation_count"]
                    )
                    app["properties"]["points"].update(minItems=1, maxItems=3)
                    revision = defs.pop("LinearRequestRevision")
                    tool["function"]["parameters"]["properties"]["request_revision"] = {
                        **revision,
                        "type": "object",
                        "description": "Omit normally. If the stored plan misread the learner's point count/outcomes, explicitly correct it with an exact goal_quote. Task, equations and coordinate mode cannot change. Every corrected candidate still undergoes full goal review.",
                    }
                    defs["CandidatePoint"]["properties"].pop("expected")
                    if plan["coordinate_mode"] == "new" and "all" in plan["point_outcomes"]:
                        defs["LinearEquation"]["properties"]["rhs"]["description"] = (
                            "For new equations, compute each rhs = a*x + b*y using the SAME chosen integer seed point that must satisfy all equations; do not choose unrelated rhs values. Preserve any equations specified by the learner."
                        )

                    tool["function"]["description"] = (
                        "Create practice following the stored linear_request. If its POINT count/outcomes misread the original goal, explicitly supply request_revision with a verbatim goal quote; otherwise preserve them. Task, equation count and construction/exact mode stay bound. Supply equations, x/y seeds, concept sources and application method. The tool constructs new points or preserves specified coordinates, computes every check, then independent course/goal review applies."
                    )
        if (
            kind == "linear_points"
            and methods
            and context.get("course_coverage", {}).get("can_answer")
            and not context.get("quality")
        ):
            # Retrieval has already supplied bounded topic/method windows. Try
            # the supported draft while two decisions remain for semantic repair.
            # A rejected draft can request missing context; no quality gate is bypassed.
            schemas = [tool for tool in schemas if tool["function"]["name"] != "read_evidence_window"]
        calls_left = context.get("budget", {}).get("model_calls_left_after_response")
        if (
            kind in {"linear_points", "python_strings"}
            and type(calls_left) is int
            and calls_left <= 2
            and any(tool["function"]["name"].startswith("create_") for tool in schemas)
        ):
            # Reserve the remaining calls for a candidate and its independent
            # review. Refusal is still available; no gate is skipped or widened.
            schemas = [
                tool
                for tool in schemas
                if tool["function"]["name"]
                not in {"search_course_evidence", "read_evidence_window", "check_python_example"}
            ]
    return schemas


class ChatProvider:
    mode = "real"

    def __init__(self, base_url=None, model=None, api_key=None):
        self.url = (os.environ.get("AGENT_LLM_BASE_URL", "") if base_url is None else base_url).rstrip("/")
        self.model = os.environ.get("AGENT_LLM_MODEL", "") if model is None else model
        self.key = os.environ.get("AGENT_LLM_API_KEY", "") if api_key is None else api_key
        if not self.url.startswith(("https://", "http://127.0.0.1:", "http://localhost:")) or not self.model:
            raise RuntimeError("Set AGENT_LLM_BASE_URL and AGENT_LLM_MODEL for Study Agent")

    def decide(self, messages, timeout):
        schemas = decision_schemas(messages)
        response = self._request(messages, schemas, timeout, 900)
        try:
            for call in response["calls"]:
                # Observed provider transport defect: an optional object was JSON
                # encoded again inside the arguments. Decode only this declared
                # object slot; never infer fields from prose or relax its schema.
                object_slots = {
                    "create_interval_practice": "worked_example",
                    "create_sequence_practice": "worked_example",
                    "search_course_evidence": "linear_request",
                    "create_python_practice": "program_plan",
                    "create_linear_practice": "request_revision",
                }
                if call["name"] in object_slots:
                    slot = object_slots[call["name"]]
                    value = call["arguments"].get(slot)
                    if isinstance(value, str) and len(value) <= 2000:
                        try:
                            decoded = json.loads(value)
                        except ValueError:
                            decoded = None
                        if isinstance(decoded, dict):
                            call["arguments"][slot] = decoded
                            response.setdefault("protocol_repairs", []).append(slot + "_json_object")
                if (
                    call["name"] == "search_course_evidence"
                    and call["arguments"].get("practice_kind") == "linear_points"
                    and not call["arguments"].get("linear_request")
                ):
                    raise ModelResponseError(
                        "MODEL_TOOL_CONTRACT",
                        response["usage"],
                        {"stage": "tool_schema", "reason": "linear_request_required"},
                    )
                arguments = call["arguments"]
                if call["name"] == "search_course_evidence" and isinstance(
                    arguments.get("linear_request"), dict
                ):
                    arguments["linear_request"].setdefault("intent_version", 2)
                    plan_input = arguments["linear_request"]
                    if (
                        plan_input.get("coordinate_mode") == "new"
                        and isinstance(plan_input.get("point_outcomes"), list)
                        and plan_input.get("point_count") != len(plan_input["point_outcomes"])
                    ):
                        raise ModelResponseError(
                            "MODEL_TOOL_CONTRACT",
                            response["usage"],
                            {
                                "stage": "tool_schema",
                                "reason": "linear_point_outcomes_count",
                                "repair": "Provide exactly one outcome per candidate point; point_count equals the list length. For exactly one of two satisfying all equations use [all,not_all]. Preserve the learner goal.",
                            },
                        )

                if call["name"] == "create_python_practice":
                    offered = next(
                        (
                            s["function"]["parameters"]
                            for s in schemas
                            if s["function"]["name"] == call["name"]
                        ),
                        {},
                    )
                    if "program_plan" in offered.get("required", []) and "program_plan" not in arguments:
                        raise ModelResponseError(
                            "MODEL_TOOL_CONTRACT",
                            response["usage"],
                            {"stage": "tool_schema", "reason": "string_program_plan_required"},
                        )
                    if "program_plan" in arguments:
                        from .contracts import compile_string_practice

                        arguments, _ = compile_string_practice(arguments)
                if (
                    call["name"] == "search_course_evidence"
                    and arguments.get("practice_kind") == "linear_points"
                    and isinstance(arguments.get("linear_request"), dict)
                    and arguments["linear_request"].get("point_count") is None
                ):
                    raise ModelResponseError(
                        "MODEL_TOOL_CONTRACT",
                        response["usage"],
                        {"stage": "tool_schema", "reason": "linear_point_count_required"},
                    )
                if call["name"] == "create_linear_practice":
                    from .linear import bind_linear_request

                    latest = next((m for m in reversed(messages) if m.get("role") == "tool"), None)
                    plan = json.loads(latest["content"]).get("linear_request") if latest else None
                    if plan:
                        try:
                            goal_message = next(m for m in messages if m.get("role") == "user")
                            arguments = bind_linear_request(
                                arguments, plan, json.loads(goal_message["content"]).get("goal")
                            )
                        except (ValueError, KeyError, TypeError):
                            raise ModelResponseError(
                                "MODEL_TOOL_CONTRACT",
                                response["usage"],
                                {
                                    "stage": "tool_schema",
                                    "reason": "learner_plan_conflict",
                                    "repair": "Preserve the original learner goal. If the stored point count/outcomes misread it, supply request_revision with an exact goal_quote, corrected point_count and one outcome per new point (or [] for specified coordinates). Otherwise keep the stored plan.",
                                },
                            ) from None
                TOOLS[call["name"]][0].model_validate(arguments)
        except ValidationError as error:
            allowed_fields = {
                "query",
                "practice_kind",
                "start_ms",
                "end_ms",
                "evidence_id",
                "title",
                "explanation",
                "evidence_ids",
                "questions",
                "reason",
                "program",
                "program_plan",
                "linear_request",
                "program_evidence_ids",
                "language",
                "concept",
                "application",
                "worked_example",
                "lower",
                "upper",
                "feedback",
                "values",
                "passes",
                "method",
            }
            failures = error.errors(include_input=False, include_url=False)
            raise ModelResponseError(
                "MODEL_TOOL_CONTRACT",
                response["usage"],
                {
                    "stage": "tool_schema",
                    "validation": [
                        {
                            "field": f["loc"][0] if f["loc"] and f["loc"][0] in allowed_fields else "other",
                            "type": f["type"],
                        }
                        for f in failures[:10]
                    ],
                },
            ) from None
        return response

    def review(self, messages, timeout):
        body = None
        try:
            body = json.loads(messages[-1]["content"])
            kind = body["candidate"]["kind"]
        except (ValueError, KeyError, IndexError, TypeError):
            kind = None
        policy = body.get("rubric_policy") if isinstance(body, dict) else None
        review_mode = body.get("review_mode") if isinstance(body, dict) else None
        from .support_review import output_tokens

        response = self._request(
            review_wire_messages(messages),
            [
                review_schema(
                    kind,
                    policy,
                    review_mode,
                    method_scope=isinstance(body, dict) and bool(body.get("application_method")),
                    context=body,
                )
            ],
            timeout,
            output_tokens(review_mode),
        )
        calls = response["calls"]
        if len(calls) != 1 or calls[0]["name"] != "assess_study_candidate":
            raise ModelResponseError("MODEL_REVIEW_CONTRACT", response["usage"], {"stage": "review_schema"})
        try:
            schema = review_contract(kind, policy, review_mode)
            verdict = schema.model_validate(calls[0]["arguments"], context=body)
        except ValidationError as error:
            # Do not log input values, model prose, arbitrary extra-field names or credentials.
            failures = error.errors(include_input=False, include_url=False)
            diagnostics = {
                "stage": "review_schema",
                "validation": [
                    {
                        "field": "issues" if failure["loc"] and failure["loc"][0] == "issues" else "other",
                        "type": failure["type"],
                    }
                    for failure in failures[:10]
                ],
            }
            raise ModelResponseError("MODEL_REVIEW_CONTRACT", response["usage"], diagnostics) from None
        if review_mode == "independent_solution":
            return {
                "solution": verdict.solution(body).model_dump(),
                "usage": response["usage"],
                "protocol_repairs": response.get("protocol_repairs", []),
            }
        review = repair_review(verdict.issues) if isinstance(verdict, AbstentionVerdict) else verdict.review()
        return {
            "review": review.model_dump(),
            "usage": response["usage"],
            "protocol_repairs": response.get("protocol_repairs", []),
        }

    def feedback(self, messages, schemas, timeout, *, review=False):
        return self._request(messages, schemas, timeout, 900)

    def _request(self, messages, schemas, timeout, max_tokens):
        deadline = time.monotonic() + timeout
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": schemas,
            "tool_choice": "required",
            "parallel_tool_calls": False,
            "temperature": 0
            if len(schemas) == 1 and schemas[0]["function"]["name"] == "assess_study_candidate"
            else 0.2,
            "max_tokens": max_tokens,
        }
        if bailian_nonthinking(self.url, self.model):
            payload["enable_thinking"] = False
            payload["tool_choice"] = (
                {"type": "function", "function": {"name": schemas[0]["function"]["name"]}}
                if len(schemas) == 1
                else "auto"
            )
        headers = {"Authorization": "Bearer " + self.key} if self.key else {}
        try:
            with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
                with client.stream(
                    "POST", self.url + "/chat/completions", json=payload, headers=headers
                ) as response:
                    response.raise_for_status()
                    body = bytearray()
                    for piece in response.iter_bytes():
                        body.extend(piece)
                        if time.monotonic() >= deadline:
                            raise BudgetExceeded()
                        if len(body) > 128 * 1024:
                            raise StudyError("MODEL_RESPONSE_LIMIT")
        except httpx.TimeoutException as error:
            if time.monotonic() >= deadline:
                raise BudgetExceeded() from error
            raise StudyError("MODEL_TIMEOUT") from error
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            code = (
                "MODEL_AUTH_FAILED"
                if status in {401, 403}
                else "MODEL_RATE_LIMITED"
                if status == 429
                else "MODEL_UNAVAILABLE"
                if status >= 500
                else "MODEL_REQUEST_REJECTED"
            )
            raise StudyError(code) from None
        except httpx.RequestError:
            raise StudyError("MODEL_UNAVAILABLE") from None
        # Optional private evaluation observer, after the normal deadline/size bounds.
        # No raw response is added to runtime events, API errors or production logs.
        observer = getattr(self, "response_observer", None)
        if observer is not None:
            observer(bytes(body))
        usage = {}
        try:
            response_data = json.loads(body)
            usage = safe_usage(response_data)
            choice = response_data["choices"][0]
            message = choice["message"]
            calls = message.get("tool_calls") or []
            if not isinstance(calls, list) or any(not isinstance(call, dict) for call in calls):
                raise ValueError("Invalid calls")
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise ModelResponseError("MODEL_INVALID_RESPONSE", usage, {"stage": "response"}) from None
        if choice.get("finish_reason") == "length":
            raise ModelResponseError(
                "MODEL_OUTPUT_TRUNCATED", usage, {"stage": "response", "finish_reason": "length"}
            )
        if not 1 <= len(calls) <= 3 or any(call.get("type") != "function" for call in calls):
            logging.getLogger(__name__).warning(
                "model_tool_contract calls=%s has_content=%s",
                len(calls),
                bool(message.get("content")),
            )
            raise ModelResponseError(
                "MODEL_TOOL_CONTRACT", usage, {"stage": "tool_contract", "reason": "call_count_or_type"}
            )
        parsed_calls, protocol_repairs = [], []
        allowed = {schema["function"]["name"] for schema in schemas}
        for call in calls:
            function = call.get("function")
            if not isinstance(function, dict) or not isinstance(function.get("name"), str):
                raise ModelResponseError(
                    "MODEL_TOOL_CONTRACT", usage, {"stage": "tool_contract", "reason": "function_shape"}
                )
            if function["name"] not in allowed:
                raise ModelResponseError(
                    "MODEL_TOOL_CONTRACT", usage, {"stage": "tool_contract", "reason": "unoffered_tool"}
                )
            try:
                arguments, repairs = tool_arguments(function.get("arguments"))
                protocol_repairs.extend(repairs)
            except (ValueError, TypeError):
                raise ModelResponseError(
                    "MODEL_TOOL_CONTRACT", usage, {"stage": "tool_contract", "reason": "arguments_json"}
                ) from None
            if not isinstance(arguments, dict):
                raise ModelResponseError(
                    "MODEL_TOOL_CONTRACT", usage, {"stage": "tool_contract", "reason": "arguments_not_object"}
                )
            parsed_calls.append({"name": function["name"], "arguments": arguments})
        return {"usage": usage, "calls": parsed_calls, "protocol_repairs": sorted(set(protocol_repairs))}


class MockProvider:
    """Deterministic demo only. Never selected as a fallback for provider failures."""

    mode = "mock"

    def feedback(self, messages, schemas, timeout, *, review=False):
        # Demo only: it intentionally makes no claim to assess semantic correctness.
        body = json.loads(messages[-1]["content"])
        if review:
            if schemas[0]["function"]["name"] == "derive_feedback_basis":
                return {
                    "calls": [
                        {
                            "name": "derive_feedback_basis",
                            "arguments": {
                                "course_covers_topic": True,
                                "explanation": "Demonstration only; no semantic assessment.",
                                "evidence_ids": [body["evidence"][0]["evidence_id"]],
                            },
                        }
                    ]
                }
            if schemas[0]["function"]["name"] == "review_feedback_insufficiency":
                return {
                    "calls": [
                        {
                            "name": "review_feedback_insufficiency",
                            "arguments": {
                                "course_covers_topic": False,
                                "reason_faithful": True,
                                "evidence_ids": [body["evidence"][0]["evidence_id"]],
                                "reason": "Demonstration only, no semantic assessment.",
                            },
                        }
                    ]
                }
            items = body["candidate"].get("observations") or [body["evidence"][0]]
            checks = [
                {
                    "index": i,
                    "source_fact": "Deterministic demonstration only.",
                    "learner_meaning": "Not semantically assessed.",
                    "observation_verdict": "accept",
                    "next_step_verdict": "accept",
                    "reason": "Demo protocol acceptance, not quality.",
                }
                for i, item in enumerate(items)
            ]
            return {"calls": [{"name": "review_answer_feedback", "arguments": {"checks": checks}}]}
        if not body["observations"]:
            return {"calls": [{"name": "read_question_evidence", "arguments": {}}]}
        return {
            "calls": [
                {
                    "name": "report_feedback_insufficient",
                    "arguments": {
                        "reason": "演示模型不判断作答内容。请结合课程证据和参考答案自行核对。",
                    },
                }
            ]
        }

    def review(self, messages, timeout):
        # Explicit demo behavior only; not a semantic quality check.
        return {"review": {"issues": [], "feedback": "Deterministic demo acceptance, not quality evidence."}}

    def decide(self, messages, timeout):
        context = json.loads(messages[-1]["content"])
        evidence = context["evidence"]
        if not evidence:
            return {"name": "search_course_evidence", "arguments": {"query": context["goal"][:500]}}
        if not any(h["tool"] == "read_evidence_window" for h in context["history"]):
            return {"name": "read_evidence_window", "arguments": {"evidence_id": evidence[0]["evidence_id"]}}
        ids = [evidence[0]["evidence_id"]]
        return {
            "name": "create_practice_set",
            "arguments": {
                "title": "演示练习（固定测试模型）",
                "explanation": "演示：请结合引用片段阅读课程内容。本输出用于验证执行与恢复流程。",
                "evidence_ids": ids,
                "questions": [
                    {
                        "question": "请用自己的话概括引用片段的主要内容。",
                        "answer_points": ["围绕引用片段的核心内容回答。"],
                        "evidence_ids": ids,
                    },
                    {
                        "question": "请从引用片段找出一个重要概念并解释。",
                        "answer_points": ["选择证据中出现的概念并解释。"],
                        "evidence_ids": ids,
                    },
                ],
            },
        }
