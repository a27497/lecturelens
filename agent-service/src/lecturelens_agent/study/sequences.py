"""Bounded selection-sort transitions, not arbitrary code execution."""

from .contracts import SequenceExample, SequencePracticeArgs, materialize_practice


def example(arguments, language):
    data = SequenceExample.model_validate(arguments).model_dump()
    values = list(data["values"])
    right = data["method"] == "largest_to_right"
    states, points = [], []
    for step in range(data["passes"]):
        boundary = len(values) - 1 - step if right else step
        indexes = range(boundary + 1) if right else range(boundary, len(values))
        selected = (max if right else min)(indexes, key=values.__getitem__)
        values[selected], values[boundary] = values[boundary], values[selected]
        region = values[boundary:] if right else values[: boundary + 1]
        states.append({"pass": step + 1, "array": list(values), "sorted_region": list(region)})
        if language == "zh":
            points.append(f"第{step + 1}轮后：{values}；已排序{'后缀' if right else '前缀'}：{region}。")
        else:
            points.append(
                f"After pass {step + 1}: {values}; sorted {'suffix' if right else 'prefix'}: {region}."
            )
    if language == "zh":
        method = (
            "在未排序前缀中找最大值，与该前缀最后一个元素交换"
            if right
            else "在未排序后缀中找最小值，与该后缀第一个元素交换"
        )
        question = f"对数组{data['values']}，每轮{method}。写出前{data['passes']}轮每轮结束后的完整数组和已排序{'后缀' if right else '前缀'}。"
        worked = f"以数组{data['values']}为例，每轮{method}。" + " ".join(points)
    else:
        method = (
            "find the largest element of the unsorted prefix and swap it with that prefix's last element"
            if right
            else "find the smallest element of the unsorted suffix and swap it with that suffix's first element"
        )
        question = f"For {data['values']}, each pass must {method}. Give the full array and sorted {'suffix' if right else 'prefix'} after EACH of the first {data['passes']} passes."
        worked = f"For {data['values']}, each pass must {method}. " + " ".join(points)
    return (
        {"question": question, "answer_points": points, "evidence_ids": data["evidence_ids"]},
        worked,
        {
            "status": "computed",
            "semantics": "selection_steps_v1",
            "problem": data,
            "states": states,
            "evidence_ids": data["evidence_ids"],
        },
    )


def sequence_practice(arguments):
    data = SequencePracticeArgs.model_validate(arguments).model_dump()
    application, _, observation = example(data["application"], data["language"])
    explanation, refs = data["explanation"], list(data["evidence_ids"])
    if "skill" in data["concept"]:
        explanation, data["concept"] = method_concept(
            data["concept"], data["application"]["method"], data["language"]
        )
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
            "questions": [data["concept"], application],
        }
    )
    return draft, {"status": "computed", "semantics": "selection_steps_v1", **observations}


def method_concept(concept, method, language):
    right = method == "largest_to_right"
    zh = language == "zh"
    if zh:
        region = "后缀" if right else "前缀"
        placement = (
            "在未排序前缀中找最大值，将其与该前缀的最后一个元素交换。"
            if right
            else "在未排序后缀中找最小值，将其与该后缀的第一个元素交换。"
        )
        boundary = (
            f"每轮固定一个最终位置，已排序{region}增加一个元素；下一轮排除这部分，只处理剩余未排序区域。"
        )
        question = {
            "boundary": "每轮结束后，下一轮应在哪个范围继续查找？为什么？",
            "placement": "每轮选中的元素应与哪个位置交换？为什么能固定一个最终位置？",
            "progress": "若本轮选中的元素已在目标位置，是否仍应缩小下一轮范围？为什么？",
        }[concept["skill"]]
        points = [placement, boundary]
        if concept["skill"] == "progress":
            points = ["应缩小范围；数组不变也已确认一个元素处于最终位置。", boundary]
    else:
        region = "suffix" if right else "prefix"
        placement = (
            "Find the maximum in the unsorted prefix and swap it with that prefix's last element."
            if right
            else "Find the minimum in the unsorted suffix and swap it with that suffix's first element."
        )
        boundary = f"Each pass fixes one final position, extending the sorted {region} by one element; exclude it and search only the remaining unsorted region next."
        question = {
            "boundary": "What range should the next pass search after each completed pass, and why?",
            "placement": "Where should each selected element be swapped, and why does this fix one final position?",
            "progress": "If the selected element is already at its destination, should the next pass still shrink its range, and why?",
        }[concept["skill"]]
        points = [placement, boundary]
        if concept["skill"] == "progress":
            points = [
                "Yes; even with no array change, one element has been confirmed in its final position.",
                boundary,
            ]
    return placement + " " + boundary, {
        "question": question,
        "answer_points": points,
        "evidence_ids": concept["evidence_ids"],
    }
