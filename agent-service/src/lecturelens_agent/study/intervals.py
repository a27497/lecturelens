"""Bounded exact interval-halving examples; conditions and answers have one source."""

from .contracts import IntervalPracticeArgs, materialize_practice


def concept_question(skill, language, evidence_ids):
    if language == "zh":
        questions = {
            "midpoint_reason": "为什么在根据更高或更低的反馈缩小搜索区间前，应先猜当前区间的中点？",
            "feedback_role": "在中点猜测后，更高或更低的反馈分别允许排除哪一侧？为什么？",
            "compare_methods": "区间减半与逐项猜测在每轮排除候选的方式上有什么区别？",
        }
        points = {
            "midpoint_reason": [
                "中点将当前区间分成等长的两半。",
                "反馈指出目标所在的一侧，因此可排除另一半区间。",
            ],
            "feedback_role": [
                "更高表示目标在猜测值之上，可排除该值及下方部分；更低则排除该值及上方部分。",
                "被排除部分不符合反馈，不可能包含目标。",
            ],
            "compare_methods": [
                "逐项猜测一次排除一个未命中的候选。",
                "区间减半根据中点处的反馈，一次排除剩余区间的一半。",
            ],
        }
    else:
        questions = {
            "midpoint_reason": "Why guess the current interval's midpoint before using higher/lower feedback to narrow the search?",
            "feedback_role": "After a midpoint guess, which side can higher or lower feedback rule out, and why?",
            "compare_methods": "How do interval halving and sequential guessing differ in what each unsuccessful guess eliminates?",
        }
        points = {
            "midpoint_reason": [
                "The midpoint divides the current interval into two equal-length halves.",
                "Feedback identifies the side containing the target, so the opposite half can be discarded.",
            ],
            "feedback_role": [
                "Higher excludes the guess and values below it; lower excludes the guess and values above it.",
                "The excluded values contradict the feedback and cannot contain the target.",
            ],
            "compare_methods": [
                "Sequential guessing eliminates one unsuccessful candidate at a time.",
                "Interval halving uses feedback at the midpoint to eliminate half of the remaining interval.",
            ],
        }
    return {"question": questions[skill], "answer_points": points[skill], "evidence_ids": list(evidence_ids)}


def example(data, language):
    low, high = data["lower"], data["upper"]
    middle = (low + high) / 2
    higher = data["feedback"] == "higher"
    left, right = (middle, high) if higher else (low, middle)
    next_middle = (left + right) / 2
    # Integer input bounds produce exact binary halves/quarters within the declared magnitude bound.
    interval = f"({left:.12g}, {right:.12g}]" if higher else f"[{left:.12g}, {right:.12g})"
    operator = ">" if higher else "<"
    if language == "zh":
        question = f"实数 x 位于闭区间 [{low}, {high}]。先猜中点 {middle:.12g}，得知 x {operator} {middle:.12g}。剩余区间是什么？下一次应取哪个中点？"
        points = [
            f"剩余区间：{interval}；先前猜测值已排除。",
            f"下一次中点：({left:.12g} + {right:.12g}) / 2 = {next_middle:.12g}。",
        ]
        worked = f"对 [{low}, {high}] 中的实数，猜中点 {middle:.12g} 后得知 x {operator} {middle:.12g}，剩余区间为 {interval}，下一次中点为 {next_middle:.12g}。"
    else:
        question = f"A real number x lies in the closed interval [{low}, {high}]. Guess its midpoint {middle:.12g} and learn x {operator} {middle:.12g}. What interval remains, and what midpoint should be guessed next?"
        points = [
            f"Remaining interval: {interval}; the previous guess is excluded.",
            f"Next midpoint: ({left:.12g} + {right:.12g}) / 2 = {next_middle:.12g}.",
        ]
        worked = f"For a real target in [{low}, {high}], guessing {middle:.12g} and learning x {operator} {middle:.12g} leaves {interval}; the next midpoint is {next_middle:.12g}."
    observation = {
        "semantics": "real_interval_halving_v1",
        "status": "computed",
        "problem": data,
        "initial_midpoint": middle,
        "remaining_interval": interval,
        "next_midpoint": next_middle,
        "evidence_ids": data["evidence_ids"],
    }
    return (
        {"question": question, "answer_points": points, "evidence_ids": data["evidence_ids"]},
        worked,
        observation,
    )


def interval_practice(arguments, evidence=None):
    data = IntervalPracticeArgs.model_validate(arguments).model_dump()
    concept = data["concept"]
    if "skill" in concept:
        concept = concept_question(concept["skill"], data["language"], concept["evidence_ids"])
    application, _, observation = example(data["application"], data["language"])
    explanation, refs = data["explanation"], list(data["evidence_ids"])
    if data["focus"] != "legacy":
        explanation = (
            "每次猜当前区间的中点，根据目标更高或更低的反馈保留对应的一半区间，再对剩余区间重复。"
            if data["language"] == "zh"
            else "Guess the current interval's midpoint, use higher/lower feedback to retain the corresponding half, and repeat on the remaining interval."
        )
        if data["focus"] == "compare_sequential":
            explanation += (
                "逐项猜测每次只排除一个候选，而区间减半每次排除剩余候选的一半。课程报告的结果："
                if data["language"] == "zh"
                else " Sequential guessing eliminates one candidate per guess, whereas halving eliminates half of those remaining. Reported course results:"
            )
            available = {item["evidence_id"]: item["text"] for item in evidence or []}
            for ref in dict.fromkeys(data["reported_evidence_ids"]):
                if ref not in available or not available[ref].strip():
                    raise ValueError("Reported results require an observed authoritative passage")
                explanation += "\n> " + available[ref][:1200]
            refs = list(dict.fromkeys([*refs, *data["reported_evidence_ids"]]))
    observations = {"application": observation}
    if data["worked_example"]:
        _, worked, observations["worked_example"] = example(data["worked_example"], data["language"])
        explanation += "\n" + worked
        refs = list(dict.fromkeys([*refs, *data["worked_example"]["evidence_ids"]]))
    draft = materialize_practice(
        {
            "title": data["title"],
            "explanation": explanation,
            "evidence_ids": refs,
            "questions": [concept, application],
        }
    )
    return draft, {"status": "computed", "semantics": "real_interval_halving_v1", **observations}
