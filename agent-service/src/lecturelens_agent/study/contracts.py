from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..contracts import Contract, Identifier
from .linear import LinearRequest, LinearSelectionArgs
from .strings import StringProgramPlan, render_string_program


class StudyScope(Contract):
    owner_id: Annotated[int, Field(ge=1)]
    course_id: Identifier
    revision: Annotated[int, Field(ge=0)]


class StudyCommand(StudyScope):
    operation: Literal[
        "CREATE_SESSION",
        "LIST",
        "RUNS",
        "START",
        "READ",
        "CANCEL",
        "EVENTS",
        "ANSWERS",
        "SAVE_ATTEMPT",
        "ATTEMPT_HISTORY",
        "START_FEEDBACK",
        "SAVE_FEEDBACK_NOTE",
        "FEEDBACK_NOTES",
    ]
    session_id: Identifier | None = None
    run_id: Identifier | None = None
    request_key: Identifier | None = None
    goal: Annotated[str, Field(min_length=1, max_length=1000)] | None = None
    after: Annotated[int, Field(ge=0)] = 0
    artifact_id: Identifier | None = None
    question_index: Annotated[int, Field(ge=0, le=1, strict=True)] | None = None
    answer_text: Annotated[str, Field(min_length=1, max_length=4000)] | None = None
    expected_version: Annotated[int, Field(ge=0, strict=True)] | None = None
    before_version: Annotated[int, Field(ge=1, strict=True)] | None = None
    attempt_id: Identifier | None = None
    feedback_id: Identifier | None = None
    note_text: Annotated[str, Field(min_length=1, max_length=2000)] | None = None
    disposition: Literal["disputed", "acknowledged"] | None = None

    @model_validator(mode="after")
    def attempt_scope(self):
        if self.operation in {"SAVE_ATTEMPT", "ATTEMPT_HISTORY", "START_FEEDBACK"}:
            if not all((self.session_id, self.run_id, self.artifact_id)) or self.question_index is None:
                raise ValueError("An attempt requires an explicit artifact and question")
        if self.operation == "SAVE_ATTEMPT":
            if not self.request_key or self.expected_version is None or not (self.answer_text or "").strip():
                raise ValueError("An attempt requires nonempty text, a request key and an expected version")
        if self.operation == "START_FEEDBACK" and not all((self.attempt_id, self.request_key)):
            raise ValueError("Feedback requires a saved answer and a request key")
        if self.operation in {"SAVE_FEEDBACK_NOTE", "FEEDBACK_NOTES"}:
            if not all((self.session_id, self.run_id, self.feedback_id)):
                raise ValueError("A feedback correction requires explicit scope")
        if self.operation == "SAVE_FEEDBACK_NOTE":
            if (
                not all((self.request_key, self.disposition, (self.note_text or "").strip()))
                or self.expected_version is None
            ):
                raise ValueError("A correction requires learner text and an expected version")
        return self


class SearchArgs(Contract):
    linear_request: Annotated[
        LinearRequest | None,
        Field(
            description="REQUIRED for linear_points: interpret learner task/counts/truth conditions BEFORE seeing course examples. Use none for every-equation-fails; all + not_all for exactly one of two points. coordinate_mode=new unless the learner supplied coordinates."
        ),
    ] = None
    query: Annotated[str, Field(min_length=1, max_length=500)]
    practice_kind: Annotated[
        Literal[
            "auto",
            "general",
            "linear_points",
            "python_output",
            "python_strings_or_code",
            "python_strings",
            "interval_halving",
            "selection_steps",
            "search_cost",
        ],
        Field(
            description="Choose subject: linear_points for checking points against linear equations, row-picture/origin/common-point exercises (not solution-set classification); python_strings for string immutability/rebinding; python_strings_or_code for other Python code; interval_halving for numeric higher/lower guessing; selection_steps for selection-sort states; search_cost for sorting preparation versus linear/binary query costs; general for other topics including tracing linear scans. Search again to change it."
        ),
    ] = "auto"
    start_ms: Annotated[int, Field(ge=0)] | None = None
    end_ms: Annotated[int, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def valid_window(self):
        if not self.query.strip() or (self.start_ms is None) != (self.end_ms is None):
            raise ValueError("Invalid query or time window")
        if self.start_ms is not None and self.start_ms > self.end_ms:
            raise ValueError("Reversed time window")
        return self


class ReadArgs(Contract):
    evidence_id: Identifier


class CheckExampleArgs(Contract):
    program: Annotated[str, Field(min_length=1, max_length=1200)]
    evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=4)]


class Question(Contract):
    question: Annotated[str, Field(min_length=5, max_length=1000)]
    answer: Annotated[str, Field(min_length=1, max_length=1500)]
    rubric: Annotated[str, Field(min_length=1, max_length=1500)]
    evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=4)]


class PracticeArgs(Contract):
    title: Annotated[str, Field(min_length=1, max_length=120)]
    explanation: Annotated[str, Field(min_length=10, max_length=4000)]
    evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=8)]
    questions: Annotated[list[Question], Field(min_length=2, max_length=2)]


class AnswerPointsQuestion(Contract):
    question: Annotated[str, Field(min_length=5, max_length=1000)]
    answer_points: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=300)]], Field(min_length=1, max_length=4)
    ]
    evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=8)]

    @model_validator(mode="after")
    def nonempty_points(self):
        if any(not point.strip() for point in self.answer_points):
            raise ValueError("Answer points must contain content")
        return self


class PracticeDraftArgs(Contract):
    title: Annotated[str, Field(min_length=1, max_length=120)]
    explanation: Annotated[str, Field(min_length=10, max_length=4000)]
    evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=8)]
    questions: Annotated[list[AnswerPointsQuestion], Field(min_length=2, max_length=2)]


class ApplicationQuestion(AnswerPointsQuestion):
    question: Annotated[
        str,
        Field(
            min_length=5,
            max_length=1000,
            description="Apply the taught method to a concrete NEW scenario, values or mistake. Do not ask to recall lecture counts or repeat the concept explanation.",
        ),
    ]


class GenericPracticeArgs(Contract):
    method_id: Literal["m1", "m2"] | None = None
    title: Annotated[str, Field(min_length=1, max_length=120)]
    explanation: Annotated[str, Field(min_length=10, max_length=4000)]
    evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=8)]
    concept: AnswerPointsQuestion
    application: ApplicationQuestion | None = None
    cost_scenario: Literal["single_lookup", "repeated_lookups"] | None = None
    application_evidence_ids: Annotated[list[Identifier], Field(max_length=8)] = []
    language: Literal["en", "zh"] = "en"

    @model_validator(mode="before")
    @classmethod
    def legacy_question_pair(cls, value):
        # Preserve existing derived-rubric replays without teaching the model
        # the old unlabelled array. Mixed shapes and free rubrics remain invalid.
        if isinstance(value, dict) and "questions" in value:
            legacy = PracticeDraftArgs.model_validate(value).model_dump()
            questions = legacy.pop("questions")
            return {**legacy, "concept": questions[0], "application": questions[1]}
        return value

    def to_draft(self):
        data = self.model_dump()
        application = data["application"]
        if self.cost_scenario:
            from .costs import cost_application

            # Generated method costs need their own shared method citations,
            # in addition to the model's selected scenario context.
            # Concept-only sources remain separate.
            refs = list(dict.fromkeys([*self.evidence_ids, *self.application_evidence_ids]))
            application = cost_application(self.cost_scenario, self.language, refs)
        return {
            **{key: data[key] for key in ("title", "explanation", "evidence_ids")},
            "questions": [data["concept"], application],
        }

    @model_validator(mode="after")
    def application_contract(self):
        if self.cost_scenario:
            if self.application is not None or not self.application_evidence_ids:
                raise ValueError("Cost mode generates its own application and needs course citations")
        elif self.application is None or self.application_evidence_ids:
            raise ValueError("General mode requires a complete application")
        return self


class StringConcept(Contract):
    skill: Literal["immutability", "rebinding"]
    evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=8)]


class PythonPracticeArgs(Contract):
    title: Annotated[str, Field(min_length=1, max_length=120)]
    explanation: Annotated[str, Field(min_length=0, max_length=4000)] = ""
    evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=8)]
    language: Literal["en", "zh"]
    concept: AnswerPointsQuestion | StringConcept
    program: Annotated[str, Field(min_length=1, max_length=800)]
    program_evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=4)]

    @model_validator(mode="after")
    def explanation_contract(self):
        if isinstance(self.concept, StringConcept):
            if self.explanation:
                raise ValueError("String mode generates its own conceptual explanation")
        elif len(self.explanation) < 10:
            raise ValueError("General Python practice needs an explanation")
        return self


class StringPracticePlanArgs(Contract):
    title: Annotated[str, Field(min_length=1, max_length=120)]
    evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=8)]
    language: Literal["en", "zh"]
    concept: StringConcept
    program_plan: StringProgramPlan
    program_evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=4)]


def compile_string_practice(arguments):
    data = StringPracticePlanArgs.model_validate(arguments).model_dump()
    plan = data.pop("program_plan")
    return {**data, "program": render_string_program(plan)}, plan


class IntervalExample(Contract):
    lower: Annotated[int, Field(ge=-1000000, le=1000000)]
    upper: Annotated[int, Field(ge=-1000000, le=1000000)]
    feedback: Literal["higher", "lower"]
    evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=4)]

    @model_validator(mode="after")
    def ordered(self):
        if self.lower >= self.upper:
            raise ValueError("The interval must have positive width")
        return self


class HalvingConcept(Contract):
    skill: Literal["midpoint_reason", "feedback_role", "compare_methods"]
    evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=8)]


class IntervalPracticeArgs(Contract):
    title: Annotated[str, Field(min_length=1, max_length=120)]
    explanation: Annotated[
        str,
        Field(
            min_length=0,
            max_length=2500,
            description="Explain the method conceptually. Put new numerical examples in worked_example, not this prose. For method comparisons include the reported lecture counts as counts only; never infer hidden target values or initial ranges.",
        ),
    ] = ""
    focus: Literal["legacy", "halving", "compare_sequential"] = "legacy"
    reported_evidence_ids: Annotated[
        list[Identifier],
        Field(
            max_length=2,
            description="For comparison, select passages reporting the lecture's observed results; the tool quotes them verbatim. Otherwise omit.",
        ),
    ] = []
    evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=8)]
    language: Literal["en", "zh"]
    concept: AnswerPointsQuestion | HalvingConcept
    application: IntervalExample
    worked_example: Annotated[
        IntervalExample | None,
        Field(
            description="Optional OBJECT with lower, upper, feedback, evidence_ids, like application; omit when no numeric example was requested. Never a prose string."
        ),
    ] = None

    @model_validator(mode="after")
    def explanation_contract(self):
        if self.focus == "legacy" and len(self.explanation) < 10:
            raise ValueError("Legacy input requires its explanation")
        if self.focus != "legacy" and self.explanation:
            raise ValueError("The tool writes the explanation for a selected focus; omit free prose")
        if self.focus == "compare_sequential" and not self.reported_evidence_ids:
            raise ValueError("Comparison requires cited lecture result passages")
        return self


class SequenceExample(Contract):
    values: Annotated[list[Annotated[int, Field(ge=-999, le=999)]], Field(min_length=2, max_length=8)]
    passes: Annotated[int, Field(ge=1, le=3)]
    method: Literal["largest_to_right", "smallest_to_left"]
    evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=4)]

    @model_validator(mode="after")
    def bounded_unique_sequence(self):
        if len(set(self.values)) != len(self.values) or self.passes >= len(self.values):
            raise ValueError("Use distinct values and fewer passes than array elements")
        return self


class SequenceConcept(Contract):
    skill: Literal["boundary", "placement", "progress"]
    evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=8)]


class SequencePracticeArgs(Contract):
    title: Annotated[str, Field(min_length=1, max_length=120)]
    explanation: Annotated[str, Field(min_length=0, max_length=2500)] = ""
    evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=8)]
    language: Literal["en", "zh"]
    concept: AnswerPointsQuestion | SequenceConcept
    application: SequenceExample
    worked_example: Annotated[
        SequenceExample | None,
        Field(
            description="Optional OBJECT for the learner's requested array. The tool computes every pass in the explanation. Omit otherwise."
        ),
    ] = None

    @model_validator(mode="after")
    def explanation_contract(self):
        if isinstance(self.concept, SequenceConcept):
            if self.explanation:
                raise ValueError("Sequence mode generates its method explanation")
            if self.worked_example and self.worked_example.method != self.application.method:
                raise ValueError("Worked and practice examples must use the same taught method")
        elif len(self.explanation) < 10:
            raise ValueError("Legacy sequence input needs an explanation")
        return self


def python_practice(arguments, observation):
    """Build a code-output question and its answer from the exact same bounded program."""
    data = PythonPracticeArgs.model_validate(arguments).model_dump()
    if "skill" in data["concept"]:
        from .strings import string_concept

        data["explanation"], data["concept"] = string_concept(data["concept"], data["language"])
    if observation.get("status") != "computed" or not observation.get("stdout"):
        raise ValueError("An output exercise needs a successfully computed nonempty output")
    if len(observation["stdout"]) > 300:
        raise ValueError("Exercise output exceeds answer-point bound")
    prompt = (
        "下面程序会依次打印什么？按顺序写出每一行输出。"
        if data["language"] == "zh"
        else "What does this program print? Write every output line in order."
    )
    return materialize_practice(
        {
            **{key: data[key] for key in ("title", "explanation", "evidence_ids")},
            "questions": [
                data["concept"],
                {
                    "question": prompt + "\n```python\n" + data["program"] + "\n```",
                    "answer_points": [observation["stdout"]],
                    "evidence_ids": data["program_evidence_ids"],
                },
            ],
        }
    )


def materialize_practice(arguments):
    """One source of truth; no independent scoring promises or negative-credit rules."""
    draft = PracticeDraftArgs.model_validate(arguments).model_dump()
    for question in draft["questions"]:
        answer = "\n".join(question["answer_points"])
        question.update(answer=answer, rubric=answer)
    return {**draft, "rubric_policy": "answer_points_v1"}


class InsufficientArgs(Contract):
    reason: Annotated[str, Field(min_length=10, max_length=400)]


TOOLS = {
    "search_course_evidence": (
        SearchArgs,
        "Search this course for relevant evidence. Use before creating practice.",
    ),
    "read_evidence_window": (ReadArgs, "Read an already selected passage and its immediate neighbors."),
    "check_python_example": (
        CheckExampleArgs,
        "Compute a small course-related Python example before drafting. Supports bounded strings, slicing, arithmetic, lists, simple functions, return and print. No imports, loops or external access. Returns actual output/variables or an explicit unsupported/error/limit observation; this does not establish course support. Cite the course passages justifying the example's operations.",
    ),
    "create_linear_practice": (
        LinearSelectionArgs,
        "Create bounded linear point-check practice. Select a conceptual skill, own citations, and the observed POINT-CHECK method for the application. Supply 1-2 nondegenerate equations a*x+b*y=rhs and 1-3 distinct integer points. Python writes the explanation/concept and computes EVERY substitution and answer; do not supply free answers. construct_points=true explicitly asks the tool to construct new distinct bounded points near the x/y seeds meeting expected constraints; never use it to alter learner-specified coordinates. Otherwise exact points are preserved. Per-point constraints (all/none/not_all/first_only/any) are checked; mismatches return actual results for repair. task=correct generates a false claim about P1 to correct. This does not teach solving arbitrary systems or classifying solution sets. Course/goal review still applies.",
    ),
    "create_python_practice": (
        PythonPracticeArgs,
        "Submit a course-grounded explanation, a concept question and a small Python program that prints output. Prefer this for Python code application goals. The program creates the output question and computes its private answer/scoring points; do not guess or supply that answer. Use only course-taught operations; the bounded interpreter allows strings, slicing, arithmetic, lists, simple functions and print, but no loops, imports, try/except or arbitrary methods. Match language to the learner's request. Quality feedback may require revision.",
    ),
    "create_interval_practice": (
        IntervalPracticeArgs,
        "Create REAL interval-halving practice. Supply closed bounds and strict higher/lower midpoint feedback; the tool computes question 2, endpoints and next midpoint without rounding. Select halving or compare_sequential; explanation is generated, comparison quotes reported_evidence_ids verbatim. Select concept.skill and its course evidence, plus an application and optional worked_example for requested numbers. Conditions are preserved. Each method/example needs its own course citations. No integer-only or unrelated goals.",
    ),
    "create_practice_set": (
        GenericPracticeArgs,
        "For skills not covered by the computed Python/interval tools, submit a grounded explanation and two distinct questions, each with private factual answer_points. These same points become the reference answer and required scoring points; do not submit separate answers, scoring conditions or rubrics. Quality feedback may require revision; only acceptance ends the run.",
    ),
    "create_sequence_practice": (
        SequencePracticeArgs,
        "Create selection-sort practice. Choose the COURSE'S method: largest_to_right or smallest_to_left. Choose a concept skill and its citations. The tool writes the method explanation/concept and computes question 2, plus optional worked_example. Use 2-8 distinct integers and 1-3 passes, fewer than elements. Each field needs its own sources; all method claims remain subject to course review.",
    ),
    "report_insufficient_evidence": (
        InsufficientArgs,
        "Submit an abstention when retrieved passages cannot support the topic. Quality feedback may require another attempt. Do not invent practice.",
    ),
}


def tool_schemas(include_time_window=True, cost_mode=False, string_mode=False):
    def compact(value):
        if isinstance(value, dict):
            return {
                key: {name: compact(schema) for name, schema in item.items()}
                if key in {"properties", "$defs"}
                else compact(item)
                for key, item in value.items()
                if key not in {"title", "default"}
            }
        if isinstance(value, list):
            return [compact(item) for item in value]
        return value

    result = [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": compact(schema.model_json_schema()),
            },
        }
        for name, (schema, description) in TOOLS.items()
    ]
    search = next(tool for tool in result if tool["function"]["name"] == "search_course_evidence")
    search["function"]["parameters"]["properties"]["practice_kind"]["enum"].remove("auto")
    search["function"]["parameters"]["properties"]["practice_kind"]["enum"].remove("python_output")
    search["function"]["parameters"]["required"].append("practice_kind")
    search_params = search["function"]["parameters"]
    description = search_params["properties"]["linear_request"]["description"]
    search_params["properties"]["linear_request"] = {
        **search_params["$defs"].pop("LinearRequest"),
        "type": "object",
        "description": description,
    }
    if not search_params["$defs"]:
        search_params.pop("$defs")
    request_schema = search_params["properties"]["linear_request"]
    request_schema["properties"].pop("intent_version")
    request_schema["properties"]["point_count"] = {
        "type": "integer",
        "minimum": 1,
        "maximum": 3,
        "description": "Number of candidate POINTS, including failing ones. For specified coordinates outcomes=[]; for new construction one outcome per point.",
    }
    request_schema["required"].append("point_count")
    request_schema["description"] = (
        "Include this object for linear_points: interpret the learner goal before retrieval. Omit the entire field for other practice kinds; do not send null or an empty string. Counts refer to candidate points, not equations; new construction has one outcome per point, specified coordinates use []."
    )

    # Put the optional nested object's fields where a tool consumer reads that
    # parameter. Some consumers omit nested $ref/anyOf details when forming calls.
    for name, example_type in [
        ("create_interval_practice", "IntervalExample"),
        ("create_sequence_practice", "SequenceExample"),
    ]:
        tool = next(tool for tool in result if tool["function"]["name"] == name)
        parameters = tool["function"]["parameters"]
        description = parameters["properties"]["worked_example"]["description"]
        parameters["properties"]["worked_example"] = {
            **parameters["$defs"][example_type],
            "type": ["object", "null"],
            "description": description,
        }
    interval = next(
        t["function"]["parameters"] for t in result if t["function"]["name"] == "create_interval_practice"
    )
    interval["properties"].pop("explanation")
    interval["properties"]["concept"] = {"$ref": "#/$defs/HalvingConcept"}
    interval["$defs"].pop("AnswerPointsQuestion", None)
    interval["properties"]["focus"]["enum"].remove("legacy")
    interval["properties"]["focus"].pop("default", None)
    interval["required"].append("focus")
    sequence = next(
        t["function"]["parameters"] for t in result if t["function"]["name"] == "create_sequence_practice"
    )
    sequence["properties"].pop("explanation")
    sequence["properties"]["concept"] = {"$ref": "#/$defs/SequenceConcept"}
    sequence["$defs"].pop("AnswerPointsQuestion", None)
    python_tool = next(t["function"] for t in result if t["function"]["name"] == "create_python_practice")
    parameters = python_tool["parameters"]
    if string_mode:
        python_tool["parameters"] = compact(StringPracticePlanArgs.model_json_schema())
        python_tool["description"] = (
            "Create course-grounded string practice from a bounded program_plan: one variable, initial literal, up to three literal or prefix+slice rebindings, and chosen print positions. No raw code, methods or mutation. The tool safely renders code and computes exact outputs. Preserve requested literals, order and counts. Concept, operations, citations and goals still require independent review."
        )
    else:
        parameters["properties"]["concept"] = {"$ref": "#/$defs/AnswerPointsQuestion"}
        parameters["$defs"].pop("StringConcept", None)
        parameters["required"].append("explanation")
    generic = next(t["function"] for t in result if t["function"]["name"] == "create_practice_set")
    parameters = generic["parameters"]
    if cost_mode:
        parameters["properties"].pop("application")
        parameters["$defs"].pop("ApplicationQuestion", None)
        parameters["properties"]["cost_scenario"] = {
            "type": "string",
            "enum": ["single_lookup", "repeated_lookups"],
        }
        parameters["required"].extend(["cost_scenario", "application_evidence_ids", "language"])
        generic["description"] = (
            "Only for taught O(n log n) sorting, O(log n) binary queries and O(n) scans. Choose single_lookup or repeated_lookups; the tool writes a correction application, no exact counts/break-even. Shared evidence_ids ground ALL method costs; application_evidence_ids add scenario context. Both are cited in the application. Supply explanation and WHY concept. Other cost models need general mode. Course support is reviewed."
        )
    else:
        for key in ("cost_scenario", "application_evidence_ids", "language"):
            parameters["properties"].pop(key)
        parameters["properties"]["application"] = {"$ref": "#/$defs/ApplicationQuestion"}
        parameters["required"].append("application")
    if not include_time_window:
        for key in ("start_ms", "end_ms"):
            search["function"]["parameters"]["properties"].pop(key, None)
    return result
