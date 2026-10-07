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
from .protocol import protocol_shape
from .quality import AbstentionVerdict, repair_review, review_contract, review_schema, review_wire_messages
from .request_budget import chat_payload
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

    def __init__(self, code, usage=None, diagnostics=None, protocol=None):
        super().__init__(code)
        self.usage = usage or {}
        self.diagnostics = diagnostics or {}
        self.private_diagnostics = (
            {**protocol, "parser_error": self.diagnostics.get("stage", "schema")} if protocol else {}
        )


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


def constrain_explanation_schemas(schemas, context, goal, prior):
    from .explanation_intent import growth_scales_needed

    growth_observation = context.get("example_check", {}).get("semantics") == "growth_scales_v1"
    reasons = {
        "position_specialization": "删除没有证据的元素位置，例如中间元素；只保留材料明确给出的比较对象。",
        "branch_specialization": "删除没有证据的递归方向或较大邻居一侧的选择；只保留材料明确给出的半规模子问题。",
        "branch_condition_specialization": "Do not assert which half contains the target without its taught selection rule.",
        "exhaustive_scan": "Complexity alone proves no all-element execution or linear traversal rule.",
        "numeric_operation_count": "Computed scales are not actual operation counts.",
        "symbolic_operation_count": "Use sourced recursion levels/halvings rather than exact total operations.",
        "subproblem_merge": "Remove untaught merge requirements or no-merge claims; retain the sourced subproblem and stopping behaviour.",
        "recursive_fanout": "Preserve the taught recursive call count; one half-size subproblem does not establish recursively solving every subproblem.",
        "exponential_speedup": "Explain exponential versus linear only under the named logarithmic reparameterization; no exponential efficiency improvement in original input size.",
        "existence_specialization": "Checking whether a named element satisfies a predicate is not a global existence test; preserve the source subject.",
        "subject_specialization": "Preserve which element is being tested; comparison neighbours are not automatically the tested subjects.",
        "predicate_condition_specialization": "删除没有证据的“若未找到/若不是峰值”分支；只描述已观察到的操作。",
        "predicate_definition": "Checking whether an element satisfies a predicate does not teach its exact inequality criterion. Keep the taught comparisons without inventing an unstated predicate definition.",
        "single_element_base": "Cite an observed source that actually describes the single-element stopping case. A complexity or timing passage alone does not establish that case; read/search the missing detail if necessary.",
        "asymptotic_value": "Theta denotes a growth class, not a scalar value. Give representative n/k scales, or map classes to Theta classes; never Theta(n)=n, Theta(log n)=k or numeric Theta values.",
        "immutability": "Cite an allowed source stating immutability for that cause/property, or remove the extra immutability claim. Rebinding alone does not prove a general mutation restriction.",
        "garbage_collection": "Remove garbage collection speculation unless an own allowed source teaches that mechanism. A lost named reference establishes neither collection nor global unreachability, even with 'may'.",
        "input_mutation_policy": "Describe the recursive input size only. It does not prove whether the original array is modified, copied, unchanged or deleted; omit an untaught mutation policy.",
        "derivation_attribution": "Label a new mathematical substitution as your derivation, not a step performed by the instructor unless the cited source actually teaches that substitution.",
        "input_precision": "保留来源中输入规模的约数表达；不要把约数或左右范围改写成精确等于。",
        "count_modality": "来源说比较次数可能达到某数时，只能说最多或可能，不要改成每步固定次数。",
    }
    rejected = {
        guard
        for check in context.get("quality", {}).get("atomic_assessments", [])
        if not check.get("supported")
        for guard in check.get("strengthening_guards", [])
    }
    for tool in schemas:
        if tool["function"]["name"] != "create_explanation":
            continue
        transaction = context.get("revision_transaction")
        if transaction:
            params = tool["function"]["parameters"]
            rejected_ids = [c["id"] for c in transaction["rejected"]]
            params["properties"] = {
                "revision_edits": {
                    "type": "array",
                    "minItems": len(rejected_ids),
                    "maxItems": len(rejected_ids),
                    "description": "For each rejected span delete, literally narrow, or reuse an exact supported_fact. Preserve immutable goal_obligations as well as protected spans. Remove unsourced positions/conditions/branches without deleting the sourced operation, input change or stopping case. Empty replacement deletes; unproved paraphrases are deleted by the server. If an obligation lacks Evidence, report insufficient evidence. The assembled answer receives full goal/atomic/Evidence/Ledger checks.",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "id": {"type": "string", "enum": rejected_ids},
                            "replacement": {"type": "string", "maxLength": 1000},
                        },
                        "required": ["id", "replacement"],
                    },
                },
            }
            params["required"] = ["revision_edits"]
            params["additionalProperties"] = False
            tool["function"]["description"] = (
                "Repair only rejected spans while preserving immutable goal_obligations and all protected supported text. Use deletion, literal narrowing or exact supported_facts; never invent missing details. Independently recheck the whole goal and sourced answer after assembly."
            )
            continue
        tool["function"]["parameters"]["properties"]["evidence_ids"]["description"] = (
            "Select sources covering EVERY premise in this answer, including operations as well as conclusions. "
            "A result or timing passage alone does not support procedural details. Original formulas govern conflicting translations; cite the track that actually states each detail, including a translation where the original excerpt is truncated."
        )
        citations = tool["function"]["parameters"]["properties"]["evidence_ids"]
        verified = context.get("quality", {}).get("verified_source_ids", [])
        if verified:
            # Preserve positive premises and their authorized sources
            # during minimal revision. A new READ releases this view;
            # independent review still checks the complete answer.
            citations["description"] = (
                "REPAIR retain previously verified sources: "
                + ",".join(verified)
                + ". "
                + citations["description"]
            )
            citations.setdefault("allOf", []).extend({"contains": {"const": ref}} for ref in verified)
        from .explanation_intent import omitted_comparison_operands

        field = tool["function"]["parameters"]["properties"]["explanation"]
        from .strengthening import _SIGNALS

        sources = [e["text"] for e in context.get("evidence", [])]
        if growth_observation:
            field["description"] = (
                "A mathematical substitution or new numeric example is YOUR derivation unless a cited passage explicitly performs it; never credit it to the course. Keep Theta on BOTH sides of class substitution: Theta(n) -> Theta(2^k), Theta(log2 n) -> Theta(k). Rows describe n and k, never Theta values, operation counts or timings. "
                + field["description"]
            )
        if sources:
            if growth_observation:
                # Keep the generation schema focused on this observed task.
                # Every Atomic/strengthening guard still runs on the answer;
                # pruning irrelevant schema prose neither accepts nor reuses it.
                domain = {"derivation_attribution", "asymptotic_value", "exponential_speedup"}
            else:
                domain = {
                    "position_specialization",
                    "branch_specialization",
                    "recursive_fanout",
                    "subproblem_merge",
                    "existence_specialization",
                    "predicate_condition_specialization",
                    "predicate_definition",
                    "garbage_collection",
                    "input_mutation_policy",
                    "derivation_attribution",
                }
                if any(re.search(r"峰值|\bpeak\b", text, re.I) for text in sources):
                    domain.add("subject_specialization")
                if any(re.search(r"算法|递归|\balgorithm\b|\brecurs", text, re.I) for text in sources):
                    domain.add("single_element_base")
                    field["description"] = (
                        "Use sourced operands/actions/stopping only; no textbook positions or branches. "
                        + field["description"]
                    )
                if growth_scales_needed(goal, prior) or any(
                    re.search(r"Θ|θ|\btheta\b", text, re.I) for text in sources
                ):
                    domain.add("asymptotic_value")
            absent = {g for g in domain if not any(_SIGNALS[g].search(text) for text in sources)}
            from .strengthening import derivation_action_observed

            if derivation_action_observed(sources):
                absent.discard("derivation_attribution")
            if absent:
                field["description"] = "Respect source gaps in the negative patterns. " + field["description"]
                field.setdefault("allOf", []).extend(
                    {"not": {"pattern": _SIGNALS[g].pattern}} for g in sorted(absent)
                )
            if "garbage_collection" in absent:
                field["description"] = "No sourced GC: no speculation, even may. " + field["description"]
        if (
            sources
            and not growth_observation
            and not any(_SIGNALS["exhaustive_scan"].search(e["text"]) for e in context.get("evidence", []))
        ):
            field["description"] = (
                "Complexity alone teaches no exhaustive traversal/count. " + field["description"]
            )
            field.setdefault("allOf", []).append({"not": {"pattern": _SIGNALS["exhaustive_scan"].pattern}})
        if omitted_comparison_operands(
            goal, "constant comparisons", [e["text"] for e in context.get("evidence", [])]
        ):
            field["description"] = (
                "具体步骤须说清材料中的比较对象（某个元素与左、右邻居）；不能只说常数次比较。若材料没有命名元素位置或递归方向，删除这些细节，保留真实比较对象。 "
                + field["description"]
            )
            field.setdefault("allOf", []).append(
                {
                    "pattern": r"左右|左.{0,24}右|邻居|相邻|\b[Ll]eft\b.{0,60}\b[Rr]ight\b|\b[Nn]eighbou?r(?:s|ing)?\b"
                }
            )
        if rejected:
            field = tool["function"]["parameters"]["properties"]["explanation"]
            field["description"] = (
                "REPAIR: "
                + " ".join(reasons[g] for g in sorted(rejected) if g in reasons)
                + " "
                + field["description"]
            )
            from .strengthening import _SIGNALS

            field["description"] = (
                "Keep supported answer spans VERBATIM; edit only rejected spans and dependent residue. "
                + field["description"]
            )
            restricted = rejected & {
                "position_specialization",
                "branch_specialization",
                "branch_condition_specialization",
            }
            for g in sorted(restricted):
                clause = {"not": {"pattern": _SIGNALS[g].pattern}}
                if clause not in field.setdefault("allOf", []):
                    field["allOf"].append(clause)
    return schemas


def decision_schemas(messages):
    first_user = next(
        (message.get("content", "") for message in messages if message.get("role") == "user"), ""
    )
    try:
        first = json.loads(first_user)
        goal = first.get("goal", "")
    except (ValueError, AttributeError, TypeError):
        goal = ""
        first = {}
    from .explanation_intent import growth_scales_needed

    prior = first.get("semantic_context", {}).get("previous_turns", [])
    schemas = tool_schemas(include_time_window=has_time_request(goal))
    context = first
    observed = any(message.get("role") == "tool" for message in messages) or bool(
        first.get("revision_transaction")
    )
    if not first.get("semantic_context", {}).get("previous_turns"):
        search = next(s for s in schemas if s["function"]["name"] == "search_course_evidence")
        search["function"]["parameters"]["properties"].pop("resolved_goal", None)
    from .goals import missing_explicit_correction_task

    if missing_explicit_correction_task(goal, ""):
        search = next(tool for tool in schemas if tool["function"]["name"] == "search_course_evidence")
        search["function"]["parameters"]["properties"]["linear_request"]["properties"]["task"]["enum"] = [
            "correct"
        ]
    if not observed:
        prior = first.get("semantic_context", {}).get("previous_turns", [])
        direct = bool(
            prior
            and (
                first.get("supported_facts")
                or (prior[-1].get("kind") == "explanation" and first.get("evidence"))
            )
        )
        names = (
            {"search_course_evidence", "create_explanation", "read_evidence_window", "compare_growth_scales"}
            if direct
            else {"search_course_evidence"}
        )
        if direct and re.search(
            r"具体|详细|细节|步骤|怎么做|\b(?:concrete|detailed|steps)\b|more detail", goal, re.I
        ):
            # A request to expand a previous answer needs an observation of its
            # taught actions, not another draft from its concise fact ledger.
            # Avoid charging an unused creation schema to that first decision;
            # READ/SEARCH still belong to the model and exercise routing stays.
            names.discard("create_explanation")
            if (
                prior[-1].get("kind") == "explanation"
                and first.get("evidence")
                and re.search(
                    r"刚才|之前|上述|第二(?:种|个)|那个|这种|这样|\b(?:second|previous|that one|it)\b",
                    goal,
                    re.I,
                )
                and not re.search(
                    r"练习|出题|自测|题目|\d+\s*道|两道|\b(?:practice|quiz|exercises?)\b", goal, re.I
                )
            ):
                # The existing referent already has authorized source handles.
                # Inspect one before deciding whether a new topic search is
                # needed; that choice is restored after the observation. This
                # leaves the bounded budget for independent repair/review.
                names = {"read_evidence_window"}
        schemas = [tool for tool in schemas if tool["function"]["name"] in names]
        try:
            first = json.loads(first_user)
        except (ValueError, TypeError):
            first = {}
        if first.get("semantic_context", {}).get("previous_turns"):
            for schema in schemas:
                if schema["function"]["name"] in {
                    "search_course_evidence",
                    "read_evidence_window",
                    "create_explanation",
                    "compare_growth_scales",
                }:
                    schema["function"]["parameters"]["required"].append("resolved_goal")
                    field = {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 1000,
                        "description": "Use the NAME of the referenced whole entity/method from previous_turns, replacing contextual words only. Preserve the entire learner request; do not narrow it to a formula term or add textbook demands. Return a standalone goal, not the raw contextual question.",
                    }
                    schema["function"]["parameters"]["properties"]["resolved_goal"] = field
                    if re.search(
                        r"刚才|之前|上述|第二(?:种|个)|那个|这种|这样|\b(?:second|previous|that one|it)\b",
                        goal,
                        re.I,
                    ):
                        field.setdefault("allOf", []).append({"not": {"const": goal}})
    else:
        latest = next(
            (message for message in reversed(messages) if message.get("role") == "tool"),
            next((message for message in messages if message.get("role") == "user"), {}),
        )
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
        if (context.get("no_progress") or (type(calls_left) is int and calls_left <= 2)) and any(
            tool["function"]["name"].startswith("create_") for tool in schemas
        ):
            # Reserve the remaining calls for a candidate and its independent
            # review. Refusal is still available; no gate is skipped or widened.
            schemas = [
                tool
                for tool in schemas
                if tool["function"]["name"]
                not in {
                    "search_course_evidence",
                    "read_evidence_window",
                    "check_python_example",
                    "compare_growth_scales",
                }
            ]
    if not growth_scales_needed(goal, prior) and not context.get("growth_scales_required"):
        # A computation observation serves a requested numerical relationship,
        # not an optional expansion of an ordinary comparison or explanation.
        schemas = [s for s in schemas if s["function"]["name"] != "compare_growth_scales"]
    if context.get("growth_scales_required"):
        # The required numerical observation must precede a free explanation.
        # The model still selects its cited premises and hypothetical inputs;
        # absent support can be reported, never supplied by this task guard.
        schemas = [s for s in schemas if s["function"]["name"] != "create_explanation"]
        from .explanation_intent import scale_forms_observed

        if not context.get("example_check") and any(
            scale_forms_observed(e["text"]) for e in context.get("evidence", [])
        ):
            # A requested mathematical illustration needs its bounded
            # observation before deciding no explanation is possible. Lexical
            # forms select this tool; they never prove teaching support.
            schemas = [
                s
                for s in schemas
                if s["function"]["name"]
                not in {"search_course_evidence", "read_evidence_window", "report_insufficient_evidence"}
            ]
    if observed:
        if context.get("output_kind") == "explanation":
            # Method planning belongs to exercise construction. Explanations
            # retain retrieval/read choices and independent atomic verification.
            schemas = [
                tool
                for tool in schemas
                if tool["function"]["name"]
                in {
                    "search_course_evidence",
                    "read_evidence_window",
                    "create_explanation",
                    "report_insufficient_evidence",
                    "compare_growth_scales",
                }
            ]
            for tool in schemas:
                if tool["function"]["name"] == "search_course_evidence":
                    # The model already chose this Run's explanation flow.
                    # Retrieval needs no exercise-construction plan. A new
                    # learner exercise request starts with the full schema.
                    params = tool["function"]["parameters"]
                    params["properties"].pop("linear_request", None)
                    params["properties"]["practice_kind"] = {"type": "string", "const": "general"}
                    params["properties"]["output_kind"] = {"type": "string", "const": "explanation"}
            schemas = constrain_explanation_schemas(schemas, context, goal, prior)
        elif not any(h.get("tool") == "create_explanation" for h in context.get("history", [])):
            schemas = [s for s in schemas if s["function"]["name"] != "compare_growth_scales"]
    if not observed and prior and prior[-1].get("kind") == "explanation":
        # Prior authorized observations already support a direct follow-up.
        # Apply the same source constraints before its first tool, without
        # fabricating an observation or forcing another READ/SEARCH.
        schemas = constrain_explanation_schemas(schemas, context, goal, prior)
    if (
        prior
        and prior[-1].get("kind") == "explanation"
        and not any(h.get("tool") == "search_course_evidence" for h in context.get("history", []))
    ):
        # Runtime requires a new topic search before refusal. A direct READ
        # can support an explanation, but cannot bypass that existing fence.
        schemas = [s for s in schemas if s["function"]["name"] != "report_insufficient_evidence"]
    for tool in schemas:
        if tool["function"]["name"] == "search_course_evidence":
            params = tool["function"]["parameters"]
            if "output_kind" not in params["required"]:
                params["required"].append("output_kind")
        if tool["function"]["name"] == "create_explanation" and context.get("generation_max_chars"):
            properties = tool["function"]["parameters"]["properties"]
            if "revision_edits" in properties:
                tool["function"]["description"] += (
                    f" Assembled answer must remain within {context['generation_max_chars']} "
                    f"characters and {context['generation_max_claims']} atomic spans, retaining supported spans verbatim."
                )
            if "evidence_ids" in properties:
                properties["evidence_ids"]["maxItems"] = context["generation_max_citations"]
                properties["title"]["maxLength"] = context["generation_max_title"]
            field = properties.get("explanation")
            if field is not None:
                field["maxLength"] = min(field["maxLength"], context["generation_max_chars"])
                field["description"] = (
                    f"Complete the current goal in at most {context['generation_max_chars']} characters "
                    f"and {context['generation_max_claims']} atomic assertion/qualification spans, "
                    f"using at most {context['generation_max_citations']} own sources. "
                    "Every span and the whole goal are independently verified; no omitted demands or extras."
                )
    if context.get("observe_before_generation"):
        schemas = [
            s for s in schemas if s["function"]["name"] in {"search_course_evidence", "read_evidence_window"}
        ]
    remaining = context.get("budget", {}).get("reserved_bytes_and_output_left")
    explanation_flow = context.get("output_kind") == "explanation" or any(
        h.get("tool") == "create_explanation" for h in context.get("history", [])
    )
    if type(remaining) is int and explanation_flow:
        request_bytes = (
            len(json.dumps(messages, ensure_ascii=False).encode()) + len(json.dumps(schemas).encode()) + 900
        )
        review_floor = (
            len(json.dumps(review_schema("explanation", review_mode="atomic_answer_spans_v2")).encode()) + 900
        )
        from .atomic_goal_spans import SPAN_SYSTEM

        # A final review also needs its verifier instructions and a bounded
        # candidate, even when the current observation has no source text yet.
        review_floor += len(SPAN_SYSTEM.encode()) + 4500 + context.get("review_source_bytes", 0)
        future = 2 * request_bytes + review_floor
        if context.get("budget", {}).get("candidates_left") == 2:
            # An optional observation must leave room for both the first
            # verification and one bounded repair, not just a perfect draft.
            future += (
                review_floor + len(json.dumps(schemas).encode()) + len(messages[0]["content"].encode()) + 900
            )
        if remaining < future:
            # Another observation requires another decision and final review.
            # This is an optimistic planning floor, not an added budget or a
            # semantic acceptance rule; actual reservations still fail closed.
            schemas = [
                s
                for s in schemas
                if s["function"]["name"]
                not in {
                    "search_course_evidence",
                    "read_evidence_window",
                    "check_python_example",
                    "compare_growth_scales",
                }
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
                revision_schema = next(
                    (
                        s["function"]["parameters"]
                        for s in schemas
                        if s["function"]["name"] == "create_explanation"
                    ),
                    {},
                )
                if call["name"] == "create_explanation" and "revision_edits" in revision_schema.get(
                    "required", []
                ):
                    from .revision import validated_edits

                    try:
                        if set(arguments) != {"revision_edits"}:
                            raise ValueError("Revision may only contain edits")
                        latest = next(
                            (m for m in reversed(messages) if m.get("role") == "tool"),
                            next((m for m in messages if m.get("role") == "user"), {}),
                        )
                        frozen = json.loads(latest["content"])["revision_transaction"]
                        validated_edits({c["id"] for c in frozen["rejected"]}, arguments["revision_edits"])
                    except (KeyError, ValueError, TypeError, StopIteration) as error:
                        raise ModelResponseError(
                            "MODEL_TOOL_CONTRACT",
                            response["usage"],
                            {"stage": "tool_schema", "reason": "bounded_revision_edits"},
                        ) from error
                else:
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
                response.get("protocol_telemetry"),
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

        expected_schema = review_schema(
            kind,
            policy,
            review_mode,
            method_scope=isinstance(body, dict) and bool(body.get("application_method")),
            context=body,
        )
        response = self._request(
            review_wire_messages(messages),
            [expected_schema],
            timeout,
            output_tokens(review_mode, body.get("relation_review") if body else False),
        )
        from .review_diagnostics import contract_detail, enabled

        trace_review = enabled(body)

        def capture_detail(errors=()):
            try:
                return contract_detail(body, response["calls"], expected_schema, errors, secrets=(self.key,))
            except Exception as capture_error:  # noqa: BLE001 -- observation cannot alter a verdict
                return {
                    "telemetry_version": "private-review-contract-v1",
                    "capture_failed": type(capture_error).__name__,
                }

        def failure_detail(failure, errors=()):
            if body and body.get("goal_scope_binding"):
                from .review_diagnostics import goal_scope_detail

                failure.private_diagnostics["goal_scope"] = goal_scope_detail(
                    body,
                    response["calls"][0].get("arguments") if response["calls"] else None,
                    errors,
                )
            if (
                review_mode
                in {
                    "answer_support_v1",
                    "atomic_answer_support_v1",
                    "atomic_delta_support_v1",
                    "atomic_answer_spans_v2",
                    "atomic_delta_spans_v2",
                }
                and errors
            ):
                if review_mode in {
                    "atomic_answer_support_v1",
                    "atomic_delta_support_v1",
                    "atomic_answer_spans_v2",
                    "atomic_delta_spans_v2",
                }:
                    from .atomic_review import citation_contract_errors
                else:
                    from .answer_review import citation_contract_errors

                failure.private_diagnostics["answer_support_contract_errors"] = citation_contract_errors(
                    body,
                    response["calls"][0]["arguments"],
                    errors,
                )
            if trace_review:
                failure.private_diagnostics["review_contract"] = capture_detail(errors)
            return failure

        calls = response["calls"]
        if len(calls) != 1 or calls[0]["name"] != "assess_study_candidate":
            raise failure_detail(
                ModelResponseError(
                    "MODEL_REVIEW_CONTRACT",
                    response["usage"],
                    {"stage": "review_schema"},
                    response.get("protocol_telemetry"),
                )
            )
        try:
            if body and body.get("goal_scope_binding"):
                from .goal_scope import ScopedGoalVerdict

                schema = ScopedGoalVerdict
            else:
                schema = review_contract(kind, policy, review_mode)
            verdict = schema.model_validate(calls[0]["arguments"], context=body)
        except ValidationError as error:
            # Do not log input values, model prose, arbitrary extra-field names or credentials.
            failures = error.errors(include_input=False, include_url=False)
            from .review_diagnostics import validation_diagnostics

            diagnostics = {
                "stage": "review_schema",
                "validation": validation_diagnostics(failures),
            }
            if (
                body
                and body.get("goal_scope_binding")
                and any(
                    f.get("loc", ())[:1] == ("goal_checks",) or "GOAL_SCOPE_VIOLATION" in f.get("msg", "")
                    for f in failures
                )
            ):
                diagnostics["goal_scope"] = "INVALID_OUTPUT_REQUIRES_BOUNDED_CORRECTION"
            raise failure_detail(
                ModelResponseError(
                    "MODEL_REVIEW_CONTRACT",
                    response["usage"],
                    diagnostics,
                    response.get("protocol_telemetry"),
                ),
                failures,
            ) from None
        if review_mode == "independent_solution":
            return {
                "solution": verdict.solution(body).model_dump(),
                "usage": response["usage"],
                "protocol_repairs": response.get("protocol_repairs", []),
                "protocol_telemetry": response.get("protocol_telemetry", {}),
            }
        review = repair_review(verdict.issues) if isinstance(verdict, AbstentionVerdict) else verdict.review()
        private = {"private_review_contract": capture_detail()} if trace_review else {}
        if body and body.get("goal_scope_binding"):
            from .review_diagnostics import goal_scope_detail

            private["private_goal_scope"] = goal_scope_detail(body, calls[0]["arguments"])
        return {
            **private,
            "review": review.model_dump(),
            "usage": response["usage"],
            "protocol_repairs": response.get("protocol_repairs", []),
            "protocol_telemetry": response.get("protocol_telemetry", {}),
        }

    def feedback(self, messages, schemas, timeout, *, review=False):
        return self._request(messages, schemas, timeout, 900)

    def _request(self, messages, schemas, timeout, max_tokens):
        deadline = time.monotonic() + timeout
        payload = chat_payload(
            self.model, messages, schemas, max_tokens, nonthinking=bailian_nonthinking(self.url, self.model)
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

        def protocol_error(code, diagnostics):
            error = ModelResponseError(code, usage, diagnostics)
            error.private_diagnostics = protocol_shape(
                bytes(body),
                schemas,
                tool_arguments,
                diagnostics.get("reason", diagnostics.get("finish_reason", diagnostics["stage"])),
            )
            return error

        try:
            response_data = json.loads(body)
            usage = safe_usage(response_data)
            choice = response_data["choices"][0]
            message = choice["message"]
            calls = message.get("tool_calls") or []
            if not isinstance(calls, list) or any(not isinstance(call, dict) for call in calls):
                raise ValueError("Invalid calls")
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise protocol_error("MODEL_INVALID_RESPONSE", {"stage": "response"}) from None
        if choice.get("finish_reason") == "length":
            raise protocol_error("MODEL_OUTPUT_TRUNCATED", {"stage": "response", "finish_reason": "length"})
        if not 1 <= len(calls) <= 3 or any(call.get("type") != "function" for call in calls):
            logging.getLogger(__name__).warning(
                "model_tool_contract calls=%s has_content=%s",
                len(calls),
                bool(message.get("content")),
            )
            raise protocol_error(
                "MODEL_TOOL_CONTRACT", {"stage": "tool_contract", "reason": "call_count_or_type"}
            )
        parsed_calls, protocol_repairs = [], []
        allowed = {schema["function"]["name"] for schema in schemas}
        for call in calls:
            function = call.get("function")
            if not isinstance(function, dict) or not isinstance(function.get("name"), str):
                raise protocol_error(
                    "MODEL_TOOL_CONTRACT", {"stage": "tool_contract", "reason": "function_shape"}
                )
            if function["name"] not in allowed:
                raise protocol_error(
                    "MODEL_TOOL_CONTRACT", {"stage": "tool_contract", "reason": "unoffered_tool"}
                )
            try:
                arguments, repairs = tool_arguments(function.get("arguments"))
                protocol_repairs.extend(repairs)
            except (ValueError, TypeError):
                raise protocol_error(
                    "MODEL_TOOL_CONTRACT", {"stage": "tool_contract", "reason": "arguments_json"}
                ) from None
            if not isinstance(arguments, dict):
                raise protocol_error(
                    "MODEL_TOOL_CONTRACT", {"stage": "tool_contract", "reason": "arguments_not_object"}
                )
            parsed_calls.append({"name": function["name"], "arguments": arguments})
        return {
            "usage": usage,
            "calls": parsed_calls,
            "protocol_repairs": sorted(set(protocol_repairs)),
            "protocol_telemetry": protocol_shape(bytes(body), schemas, tool_arguments),
        }


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
            arguments = {"query": context["goal"][:500]}
            if context.get("semantic_context", {}).get("previous_turns"):
                arguments["resolved_goal"] = context["goal"]
            return {"name": "search_course_evidence", "arguments": arguments}
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
