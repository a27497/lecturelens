"""Bounded point checks; computation never establishes course support."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..contracts import Contract, Identifier

SmallInt = Annotated[int, Field(strict=True, ge=-20, le=20)]


class LinearRequest(Contract):
    """Model interpretation of the learner request before seeing course examples."""

    intent_version: Literal[1, 2] = 1
    task: Annotated[
        Literal["verify", "correct"],
        Field(
            description="correct for correcting an error or misconception (纠错、纠正常见误解); verify only when no correction is requested."
        ),
    ]
    point_count: Annotated[
        int | None,
        Field(
            ge=1,
            le=3,
            strict=True,
            description="Number of candidate POINTS requested, not equations or valid solutions. Two candidate points means 2.",
        ),
    ] = None
    equation_count: Annotated[int, Field(strict=True, ge=1, le=2)]
    point_outcomes: Annotated[
        list[Literal["any", "all", "none", "not_all", "first_only"]],
        Field(
            max_length=3,
            description="For NEW points, exactly ONE outcome PER point: list length must equal point_count. E.g. exactly one of two points succeeds => [all,not_all], neither equation holds for one point => [none]. For specified coordinates return []: observe truth instead of guessing.",
        ),
    ]
    coordinate_mode: Literal["new", "specified"]

    @model_validator(mode="after")
    def one_outcome_per_point(self):
        if self.intent_version == 2 and self.coordinate_mode == "specified":
            if self.point_count is None:
                raise ValueError("Fixed inputs require an explicit point count")
            return self
        if not self.point_outcomes:
            raise ValueError("New point construction needs outcomes")
        if self.point_count is not None and self.point_count != len(self.point_outcomes):
            raise ValueError(
                "point_outcomes needs ONE entry PER candidate point; exactly one of two succeeds => [all, not_all]"
            )
        return self


class LinearRequestRevision(Contract):
    goal_quote: Annotated[
        str,
        Field(
            min_length=1,
            max_length=300,
            description="Exact learner-goal quote justifying a corrected POINT count or per-point outcomes; no paraphrase.",
        ),
    ]
    point_count: Annotated[int, Field(strict=True, ge=1, le=3)]
    point_outcomes: Annotated[
        list[Literal["any", "all", "none", "not_all", "first_only"]],
        Field(max_length=3, description="For new points one entry per point; for specified coordinates []."),
    ]


def revised_linear_request(arguments, request, goal=None):
    from copy import deepcopy

    result = deepcopy(request)
    revision = arguments.get("request_revision")
    if revision is None:
        return result
    revision = LinearRequestRevision.model_validate(revision)
    if not goal or revision.goal_quote not in goal:
        raise ValueError("A plan correction requires an exact original goal quote")
    result.update(point_count=revision.point_count, point_outcomes=revision.point_outcomes)
    LinearRequest.model_validate(result)
    return result


def bind_linear_request(arguments, request, goal=None):
    from copy import deepcopy

    request = LinearRequest.model_validate(revised_linear_request(arguments, request, goal))
    result = deepcopy(arguments)
    application = result["application"]
    fixed_inputs = request.intent_version == 2 and request.coordinate_mode == "specified"
    count = request.point_count if fixed_inputs else len(request.point_outcomes)
    if len(application["equations"]) != request.equation_count or len(application["points"]) != count:
        raise ValueError("Application counts must preserve the pre-retrieval learner plan")
    fixed = {"task": request.task, "construct_points": request.coordinate_mode == "new"}
    for key, value in fixed.items():
        if key in application and application[key] != value:
            raise ValueError("Application cannot silently replace its learner plan")
        application[key] = value
    outcomes = ["any"] * count if fixed_inputs else request.point_outcomes
    for point, outcome in zip(application["points"], outcomes, strict=True):
        if "expected" in point and point["expected"] != outcome:
            raise ValueError("Point outcomes must preserve the learner plan")
        point["expected"] = outcome
    return result


class LinearEquation(Contract):
    a: SmallInt
    b: SmallInt
    rhs: Annotated[int, Field(strict=True, ge=-100, le=100)]

    @model_validator(mode="after")
    def nondegenerate(self):
        if not (self.a or self.b):
            raise ValueError("A line needs a nonzero coefficient")
        return self


class CandidatePoint(Contract):
    x: SmallInt
    y: SmallInt
    expected: Literal["any", "all", "none", "not_all", "first_only"] = "any"


class PointProblem(Contract):
    construct_points: Annotated[
        bool,
        Field(
            strict=True,
            description="True for designing NEW coordinates from x/y seeds; false only when keeping specified coordinates exactly.",
        ),
    ] = False
    equations: Annotated[list[LinearEquation], Field(min_length=1, max_length=2)]
    points: Annotated[list[CandidatePoint], Field(min_length=1, max_length=3)]
    task: Annotated[
        Literal["verify", "correct"],
        Field(
            description="Use correct when the learner requests an error-correction exercise; otherwise verify."
        ),
    ]
    evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=8)]

    @model_validator(mode="after")
    def distinct_points(self):
        if not self.construct_points and len({(point.x, point.y) for point in self.points}) != len(
            self.points
        ):
            raise ValueError("Candidate points must be distinct")
        return self


class LinearConcept(Contract):
    """Cite passages teaching this concept, not just a worked substitution."""

    skill: Literal["row_picture", "system_solution", "origin", "coordinates"]
    evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=8)]


class LinearSelectionArgs(Contract):
    request_revision: LinearRequestRevision | None = None
    method_id: Literal["m1", "m2"]
    language: Literal["zh", "en"]
    concept: LinearConcept
    application: PointProblem


class LinearPracticeArgs(LinearSelectionArgs):
    # Bound from the model-selected concept and observed application method.
    evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=8)]


CONCEPTS = {
    "zh": {
        "row_picture": (
            "在 row picture 中，一个二元一次方程被表示为 xy 平面上的一条直线。直线上的点满足对应方程，可以通过代入坐标检查。",
            "在 row picture 中，一个二元一次方程的直线表示什么？如何核对一个点是否在这条直线上？",
            [
                "直线表示满足该方程的点。",
                "将点的坐标分别代入 x 和 y，核对等式是否成立。",
            ],
        ),
        "system_solution": (
            "方程组的解同时满足所有方程，在图中对应这些直线的公共点。只检验其中一个方程还不足以确认一个点是方程组的解。",
            "为什么方程组的解要对应各条直线的公共点，而仅在一条直线上还不够？",
            [
                "在某条直线上表示满足对应的方程。",
                "方程组的解必须同时满足所有方程，因此必须同时在各条直线上。",
            ],
        ),
        "origin": (
            "原点的坐标是 (0,0)。将 x=0、y=0 代入方程，等式成立就表明对应直线经过原点。",
            "如何用代入的方法判断一条方程所表示的直线是否经过原点？",
            ["将原点坐标 (0,0) 代入方程。", "等式成立表示原点在直线上，否则不在。"],
        ),
        "coordinates": (
            "点 (x,y) 中，第一个数对应 x，第二个数对应 y。代入方程时保留这个顺序，再比较等式两边。",
            "代入坐标时如何避免把横坐标与纵坐标放错位置？为什么要保留顺序？",
            [
                "将第一个坐标代入 x，第二个坐标代入 y。",
                "调换坐标可能改变被检验的点及判断结果。",
            ],
        ),
    },
    "en": {
        "row_picture": (
            "In the row picture, a linear equation is represented by a line in the xy-plane. Its points satisfy the equation and can be checked by substitution.",
            "What does an equation's line represent in the row picture, and how can you check a point on it?",
            [
                "The line represents points satisfying the equation.",
                "Substitute the point's x and y coordinates and check the equality.",
            ],
        ),
        "system_solution": (
            "A system's solution satisfies every equation and lies on all their lines. Checking only one equation is insufficient to confirm a solution.",
            "Why must a system's solution lie on every line, rather than just one?",
            [
                "Lying on a line means satisfying its equation.",
                "A solution must satisfy all equations and therefore lie on all their lines.",
            ],
        ),
        "origin": (
            "The origin has coordinates (0,0). Substitute x=0 and y=0: if the equality holds, the equation's line passes through the origin.",
            "How can substitution determine whether an equation's line passes through the origin?",
            [
                "Substitute (0,0) into the equation.",
                "The origin lies on the line exactly when the equality holds.",
            ],
        ),
        "coordinates": (
            "In a point (x,y), the first number is x and the second is y. Preserve that order when substituting, then compare both sides.",
            "How do you avoid swapping coordinates during substitution, and why does the order matter?",
            [
                "Substitute the first coordinate for x and the second for y.",
                "Swapping coordinates may change the point and the result.",
            ],
        ),
    },
}


def equation_text(equation):
    terms = []
    for coefficient, variable in [(equation.a, "x"), (equation.b, "y")]:
        if not coefficient:
            continue
        term = (str(abs(coefficient)) if abs(coefficient) != 1 else "") + variable
        terms.append(
            ("-" if coefficient < 0 else "") + term
            if not terms
            else (" - " if coefficient < 0 else " + ") + term
        )
    return "".join(terms) + f" = {equation.rhs}"


def point_matches(expected, truth):
    return {
        "any": True,
        "all": all(truth),
        "none": not any(truth),
        "not_all": not all(truth),
        "first_only": len(truth) == 2 and truth[0] and not truth[1],
    }[expected]


def point_application(problem, language):
    problem = PointProblem.model_validate(problem)
    requested = problem.model_dump()
    if problem.construct_points:
        chosen = []
        for seed in problem.points:
            # Explicit generation mode: x/y are starting seeds, not promised
            # learner coordinates. Search at most 41*41 bounded integer points.
            options = sorted(
                ((x, y) for x in range(-20, 21) for y in range(-20, 21)),
                key=lambda xy: (abs(xy[0] - seed.x) + abs(xy[1] - seed.y), xy),
            )
            for x, y in options:
                if (x, y) in {(p.x, p.y) for p in chosen}:
                    continue
                truth = [eq.a * x + eq.b * y == eq.rhs for eq in problem.equations]
                if point_matches(seed.expected, truth):
                    chosen.append(seed.model_copy(update={"x": x, "y": y}))
                    break
            else:
                # A suggestion is an observation, never an automatic change to
                # the model's equations or learner-specified values.
                suggested = (
                    [
                        eq.model_copy(update={"rhs": eq.a * seed.x + eq.b * seed.y}).model_dump()
                        for eq in problem.equations
                    ]
                    if seed.expected == "all"
                    else []
                )
                if any(abs(eq["rhs"]) > 100 for eq in suggested):
                    suggested = []
                return None, {
                    "repair_hint": "No bounded integer point satisfies the requested condition. Change the draft; repeating it cannot succeed. If authoring NEW equations, the suggested RHS values make this seed satisfy all; never replace learner-specified equations.",
                    "suggested_new_equations": suggested,
                    "semantics": "linear_point_checks_v1",
                    "status": "constraint_mismatch",
                    "requested_problem": requested,
                    "problem": requested,
                    "language": language,
                    "checks": [],
                    "constraints_met": [False],
                }
        problem = problem.model_copy(update={"points": chosen, "construct_points": False})
    checks = [
        [
            {
                "lhs": eq.a * point.x + eq.b * point.y,
                "rhs": eq.rhs,
                "holds": eq.a * point.x + eq.b * point.y == eq.rhs,
            }
            for eq in problem.equations
        ]
        for point in problem.points
    ]
    matches = []
    for point, results in zip(problem.points, checks, strict=True):
        truth = [result["holds"] for result in results]
        matches.append(point_matches(point.expected, truth))
    equations = "; ".join(f"({i + 1}) {equation_text(eq)}" for i, eq in enumerate(problem.equations))
    points = "; ".join(f"P{i + 1}=({point.x},{point.y})" for i, point in enumerate(problem.points))
    if language == "zh":
        question = f"给定方程：{equations}。候选点：{points}。"
        if problem.task == "correct":
            claim = "不满足" if all(result["holds"] for result in checks[0]) else "满足"
            question += f"有同学声称 P1 {claim}上述所有方程。"
        question += "请将每个点代入每个方程，写出各次检验结果，并判断每个点是否满足所有方程。"
        if problem.task == "correct":
            question += "据此纠正该同学的说法。"
    else:
        question = f"Equations: {equations}. Candidate points: {points}. "
        if problem.task == "correct":
            claim = "does not satisfy" if all(result["holds"] for result in checks[0]) else "satisfies"
            question += f"A student claims P1 {claim} all these equations. "
        question += "Substitute every point into every equation, report every check, and decide whether each point satisfies all equations."
        if problem.task == "correct":
            question += " Correct the student's claim."
    answers = []
    for i, (point, results) in enumerate(zip(problem.points, checks, strict=True)):
        steps = [
            f"({j + 1}) ({eq.a})×({point.x}) + ({eq.b})×({point.y}) = {result['lhs']} "
            f"{'=' if result['holds'] else '≠'} {eq.rhs}"
            for j, (eq, result) in enumerate(zip(problem.equations, results, strict=True))
        ]
        conclusion = (
            ("满足所有方程" if all(r["holds"] for r in results) else "不满足所有方程")
            if language == "zh"
            else (
                "satisfies all equations"
                if all(r["holds"] for r in results)
                else "does not satisfy all equations"
            )
        )
        answers.append(f"P{i + 1}=({point.x},{point.y}): " + "; ".join(steps) + f"; {conclusion}.")
    return {
        "question": question,
        "answer_points": answers,
        "evidence_ids": problem.evidence_ids,
    }, {
        "semantics": "linear_point_checks_v1",
        "status": "computed" if all(matches) else "constraint_mismatch",
        "problem": problem.model_dump(),
        "requested_problem": requested,
        "language": language,
        "checks": checks,
        "constraints_met": matches,
    }


def linear_practice(arguments):
    from .contracts import materialize_practice

    args = LinearPracticeArgs.model_validate(arguments)
    application, observation = point_application(args.application, args.language)
    if observation["status"] != "computed":
        return None, observation
    explanation, question, points = CONCEPTS[args.language][args.concept.skill]
    return materialize_practice(
        {
            "title": "直线方程与点的检验"
            if args.language == "zh"
            else "Checking points against linear equations",
            "explanation": explanation,
            "evidence_ids": args.evidence_ids,
            "questions": [
                {
                    "question": question,
                    "answer_points": points,
                    "evidence_ids": args.concept.evidence_ids,
                },
                application,
            ],
        }
    ), observation


def effective_linear_request(request):
    """Show effective constraints; retain original model hypotheses in the journal."""
    from copy import deepcopy

    result = deepcopy(request)
    if result.get("intent_version", 1) == 2 and result.get("coordinate_mode") == "specified":
        result["point_outcomes"] = []
    return result
