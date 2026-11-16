import hashlib
import json

from .context import aliases_in, has_time_request
from .contracts import TOOLS, GenericPracticeArgs, compile_string_practice
from .errors import StudyError
from .linear import LinearPracticeArgs, bind_linear_request, revised_linear_request
from .method_scope import latest_coverage

CANDIDATE_TOOLS = {
    "create_practice_set",
    "create_linear_practice",
    "create_python_practice",
    "create_interval_practice",
    "create_sequence_practice",
}
ARTIFACT_TOOLS = CANDIDATE_TOOLS | {"report_insufficient_evidence"}
# Presentation-only fields: changing them alone cannot address a quality rejection.
PRESENTATION_FIELDS = {"title"}


def candidate_substance(name, arguments, application_method=None):
    content = {key: value for key, value in arguments.items() if key not in PRESENTATION_FIELDS}
    return hashlib.sha256(
        json.dumps([name, content, application_method], sort_keys=True).encode()
    ).hexdigest()


def unchanged_rejected_candidate(history, name, arguments, application_method):
    """Index of an earlier rejected candidate with the same substance, if any."""
    if name not in CANDIDATE_TOOLS:
        return None
    substance = candidate_substance(name, arguments, application_method)
    for index, item in enumerate(history):
        if (
            item["tool"] == name
            and item["result"].get("quality", {}).get("accepted") is False
            and candidate_substance(name, item["arguments"], item["result"].get("application_method"))
            == substance
        ):
            return index
    return None


def prepare_tool_call(name, raw_arguments, *, goal, history, aliases):
    """Build the checkpoint payload from the model call and its decision context."""
    arguments, program_plan, revised_request = _normalize_arguments(
        name, raw_arguments, goal, history, aliases
    )
    arguments, application_method = _bind_practice_evidence(name, arguments, history, aliases)
    _validate_references(name, arguments, history, aliases)
    fingerprint = hashlib.sha256(
        json.dumps(
            [name, arguments, application_method] if application_method else [name, arguments],
            sort_keys=True,
        ).encode()
    ).hexdigest()

    return {
        "name": name,
        "arguments": arguments,
        "fingerprint": fingerprint,
        "evidence_aliases": aliases,
        **({"program_plan": program_plan} if program_plan is not None else {}),
        **({"linear_request": revised_request} if revised_request is not None else {}),
        **({"application_method": application_method} if application_method else {}),
    }


def _normalize_arguments(name, raw_arguments, goal, history, aliases):
    raw_arguments = dict(raw_arguments)
    program_plan = None
    revised_request = None
    if name == "create_python_practice" and "program_plan" in raw_arguments:
        raw_arguments, program_plan = compile_string_practice(raw_arguments)
    request_plan = next(
        (h["result"]["linear_request"] for h in reversed(history) if h["result"].get("linear_request")),
        None,
    )
    if (
        name == "search_course_evidence"
        and request_plan is None
        and isinstance(raw_arguments.get("linear_request"), dict)
    ):
        raw_arguments["linear_request"] = {**raw_arguments["linear_request"], "intent_version": 2}
    if (
        name == "create_linear_practice"
        and raw_arguments.get("request_revision") is not None
        and not request_plan
    ):
        raise StudyError("LEARNER_PLAN_CONFLICT")
    if name == "create_linear_practice" and request_plan:
        try:
            if raw_arguments.get("request_revision") is not None:
                revised_request = revised_linear_request(raw_arguments, request_plan, goal)
            raw_arguments = bind_linear_request(raw_arguments, request_plan, goal)
        except (ValueError, KeyError, TypeError) as error:
            raise StudyError("LEARNER_PLAN_CONFLICT") from error
    if name == "search_course_evidence" and request_plan:
        if raw_arguments.get("linear_request") not in (None, request_plan):
            raise StudyError("LEARNER_PLAN_CONFLICT")
        if raw_arguments.get("practice_kind") == "linear_points":
            raw_arguments["linear_request"] = request_plan
    if name == "search_course_evidence":
        # Validate even filters that will be removed by the goal fence.
        TOOLS[name][0].model_validate(aliases_in(raw_arguments, aliases))
    if name == "search_course_evidence" and not has_time_request(goal):
        # Unrequested filters must not turn a relevant course into a false abstention.
        raw_arguments.pop("start_ms", None)
        raw_arguments.pop("end_ms", None)
    arguments = (
        TOOLS[name][0].model_validate(aliases_in(raw_arguments, aliases)).model_dump(exclude_none=True)
    )
    return arguments, program_plan, revised_request


def _bind_practice_evidence(name, arguments, history, aliases):
    application_method = None
    if name in {"create_practice_set", "create_linear_practice"}:
        coverage = latest_coverage(history)
        methods = coverage.get("methods") if coverage is not None else None
        method_id = arguments.get("method_id")
        if methods is not None:
            if method_id not in methods:
                raise StudyError("APPLICATION_METHOD_REQUIRED")
            application_method = methods[method_id]
            if application_method["evidence_id"] not in aliases.values():
                raise StudyError("METHOD_EVIDENCE_NOT_SELECTED")
        elif method_id is not None:
            raise StudyError("UNOBSERVED_APPLICATION_METHOD")
        if name == "create_linear_practice":
            # A template combines the selected concept with the selected
            # checking operation. Bind both sources before review/journaling.
            method_source = application_method["evidence_id"]
            if arguments["concept"]["skill"] == "system_solution":
                pins = next(
                    (
                        h["result"].get("concept_evidence_ids", [])
                        for h in reversed(history)
                        if h["tool"] == "search_course_evidence"
                    ),
                    [],
                )
                # The selected joint-solution template depends on this
                # retrieved concept context as well as the point-check
                # method. Bind visible, owned sources; review still
                # decides whether their text actually supports it.
                arguments["concept"]["evidence_ids"] = list(
                    dict.fromkeys(
                        [
                            *arguments["concept"]["evidence_ids"],
                            *(ref for ref in pins if ref in aliases.values()),
                        ]
                    )
                )
            for part in (arguments["concept"], arguments["application"]):
                part["evidence_ids"] = list(dict.fromkeys([*part["evidence_ids"], method_source]))
            arguments["evidence_ids"] = arguments["concept"]["evidence_ids"]
            arguments = LinearPracticeArgs.model_validate(arguments).model_dump()
        if name == "create_practice_set":
            arguments = GenericPracticeArgs.model_validate(arguments).to_draft()
            if application_method is not None:
                # As for linear practice: the chosen method_id names the source of
                # the application's operation, so question_2 cites it before review.
                # The source is already authorized (METHOD_EVIDENCE_NOT_SELECTED) and,
                # like every citation, one of at most eight visible aliases, so the
                # question's bound holds. Review still judges method alignment and
                # support. method_citation_check remains for checkpointed candidates
                # decided before this binding.
                application = arguments["questions"][1]
                application["evidence_ids"] = list(
                    dict.fromkeys([*application["evidence_ids"], application_method["evidence_id"]])
                )
    return arguments, application_method


def _validate_references(name, arguments, history, aliases):
    referenced = set(arguments.get("evidence_ids", []))
    if name == "read_evidence_window":
        referenced.add(arguments["evidence_id"])
    for question in arguments.get("questions", []):
        referenced.update(question["evidence_ids"])
    if name == "create_python_practice":
        referenced.update(arguments["concept"]["evidence_ids"])
        referenced.update(arguments["program_evidence_ids"])
    if name in {"create_interval_practice", "create_sequence_practice", "create_linear_practice"}:
        referenced.update(arguments.get("reported_evidence_ids", []))
        referenced.update(arguments["concept"]["evidence_ids"])
        referenced.update(arguments["application"]["evidence_ids"])
        if arguments.get("worked_example"):
            referenced.update(arguments["worked_example"]["evidence_ids"])
    if not referenced <= set(aliases.values()):
        raise StudyError("UNSUPPORTED_CITATION")
    if name in ARTIFACT_TOOLS and not any(item["tool"] == "search_course_evidence" for item in history):
        raise StudyError("SEARCH_REQUIRED")
