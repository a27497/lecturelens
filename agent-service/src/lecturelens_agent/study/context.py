"""Bounded model context; aliases are per-decision and never used as stored provenance."""

import json
import re
from copy import deepcopy


def has_time_request(goal):
    return bool(
        re.search(
            r"\d{1,2}:\d{2}|(?:\d+(?:\.\d+)?|[一二三四五六七八九十百]+)\s*(?:分钟|秒|minutes?|mins?|seconds?|secs?)",
            goal,
            re.IGNORECASE,
        )
    )


def compact_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def aliases_in(value, mapping):
    if isinstance(value, dict):
        return {
            key: mapping.get(item, item)
            if (key == "evidence_id" or (key == "source" and "quote" in value)) and isinstance(item, str)
            else [mapping.get(ref, ref) for ref in item]
            if key
            in {
                "evidence_ids",
                "program_evidence_ids",
                "reported_evidence_ids",
                "application_evidence_ids",
                "concept_evidence_ids",
            }
            and isinstance(item, list)
            else aliases_in(item, mapping)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [aliases_in(item, mapping) for item in value]
    return value


def retain_evidence(selected, observed):
    """A reread refreshes the whole observed window, including existing IDs."""
    latest = list(dict.fromkeys(observed))
    return [*[key for key in selected if key not in latest], *latest][-8:]


def unfinished_speech(item):
    text = item.get("text", "").strip()
    return bool(text) and not re.search(r"[.!?。！？][\"'’”）)]*$", text)


def include_citation_neighbors(draft, evidence):
    """Cite adjacent, already selected speech context without inventing merged Evidence IDs."""
    result = deepcopy(draft)
    by_id = {item["evidence_id"]: item for item in evidence}
    neighbors = {}
    following = {}
    for kind in ("SUBTITLE", "SUBTITLE_TRANSLATION"):
        ordered = sorted(
            (item for item in evidence if item.get("source_type") == kind),
            key=lambda item: (item["start_ms"], item["end_ms"], item["evidence_id"]),
        )
        for left, right in zip(ordered, ordered[1:], strict=False):
            if 0 <= right["start_ms"] - left["end_ms"] <= 3000:
                neighbors.setdefault(left["evidence_id"], []).append(right["evidence_id"])
                neighbors.setdefault(right["evidence_id"], []).append(left["evidence_id"])
                following[left["evidence_id"]] = right["evidence_id"]
    for field in [result, *result["questions"]]:
        original = field["evidence_ids"]
        if not set(original) <= by_id.keys():
            raise ValueError("Citation must already be selected and authorized")
        field["evidence_ids"] = list(
            dict.fromkeys(
                [
                    *original,
                    *(ref for key in original for ref in neighbors.get(key, [])),
                ]
            )
        )
        # A subtitle boundary may cut one sentence across several chunks. Follow
        # only contiguous, already authorized speech until its sentence ends.
        for key in list(field["evidence_ids"]):
            while unfinished_speech(by_id[key]) and key in following:
                key = following[key]
                if key not in field["evidence_ids"]:
                    field["evidence_ids"].append(key)
        if len(field["evidence_ids"]) > 8:
            raise ValueError("Citation context exceeds the visible Evidence bound")
    return result


def evidence_gaps(evidence, *, general=False):
    """At most two windows: internal speech gaps, then an unfinished trailing sentence."""
    gaps = []
    tails = []
    if len(evidence) >= 8:
        return gaps
    for kind in ("SUBTITLE", "SUBTITLE_TRANSLATION"):
        ordered = sorted(
            (item for item in evidence if item.get("source_type") == kind),
            key=lambda item: (item["start_ms"], item["end_ms"]),
        )
        for left, right in zip(ordered, ordered[1:], strict=False):
            width = right["start_ms"] - left["end_ms"]
            if 0 < width and (width <= 60000 or general):
                gaps.append(
                    (
                        min(width, 60000),
                        left["evidence_id"],
                        left["end_ms"],
                        min(right["start_ms"], left["end_ms"] + 60000),
                        kind,
                        "gap",
                    )
                )
        if ordered and unfinished_speech(ordered[-1]):
            last = ordered[-1]
            tails.append(
                (60000, last["evidence_id"], last["end_ms"], last["end_ms"] + 60000, kind, "continuation")
            )
    return (sorted(gaps, key=(lambda gap: (gap[2], gap[0])) if general else None) + tails)[:2]


def repair_observation(quality):
    """Keep full observations in the journal; avoid re-sending repeated course quotes."""
    if not quality.get("goal_assessments"):
        return quality  # Historical replay contracts retain their original view.
    visible = {
        k: quality[k]
        for k in (
            "accepted",
            "source",
            "issues",
            "feedback",
            "factual_check",
            "goal_assessments",
            "rule_observations",
            "explanation_assessments",
            "method_assessment",
        )
        if k in quality
    }
    visible["field_evidence_ids"] = {
        field: [quote["source"] for quote in grounds] for field, grounds in quality.get("grounds", {}).items()
    }
    visible["answer_observations"] = [
        {k: v for k, v in answer.items() if k != "grounds"}
        for answer in quality.get("answer_observations", [])
    ]
    return visible


def decision_observation(result):
    # The journal keeps raw source quotes. Visible Evidence already supplies the text.
    visible = dict(result)
    if visible.get("linear_request"):
        from .linear import effective_linear_request

        visible["linear_request"] = effective_linear_request(visible["linear_request"])
    if "course_coverage" in visible:
        coverage = dict(visible["course_coverage"])
        if "methods" in coverage:
            coverage["methods"] = {
                key: {k: v for k, v in method.items() if k != "quote"}
                for key, method in coverage["methods"].items()
            }
        visible["course_coverage"] = coverage
    if "quality" in visible:
        visible["quality"] = repair_observation(visible["quality"])
    return visible


def visible_references(value, selected):
    """Project citations onto current context; the durable journal remains unchanged."""
    if isinstance(value, list):
        return [visible_references(item, selected) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key in {
            "evidence_ids",
            "program_evidence_ids",
            "reported_evidence_ids",
            "application_evidence_ids",
            "concept_evidence_ids",
            "context_windows",
        } and isinstance(item, list):
            result[key] = [ref for ref in item if ref in selected]
        elif key == "evidence_id" and isinstance(item, str):
            result[key] = item if item in selected else "not_selected"
        elif key == "methods" and isinstance(item, dict):
            result[key] = {
                name: visible_references(method, selected)
                for name, method in item.items()
                if method.get("evidence_id") in selected
            }
        else:
            result[key] = visible_references(item, selected)
    return result


def build_messages(system, goal, evidence, history, previous_turns, budget=None):
    # Source and translated evidence often cover the identical video interval.
    # Keep one copy in the prompt; canonical IDs remain in the runtime checkpoint.
    visible, intervals = [], set()
    for item in evidence:
        source = item.get("source_type", "SUBTITLE")
        group = "speech" if source in {"SUBTITLE", "SUBTITLE_TRANSLATION"} else item["evidence_id"]
        interval = (group, item["start_ms"], item["end_ms"])
        if interval not in intervals:
            intervals.add(interval)
            visible.append(item)
    visible = visible[-8:]
    forward = {item["evidence_id"]: f"e{i + 1}" for i, item in enumerate(evidence)}
    selected = {item["evidence_id"] for item in visible}
    # Earlier tool results may refer to deduplicated candidates. Keep those references short,
    # but only the aliases with actual visible text are accepted as returned citations.
    reverse = {forward[item["evidence_id"]]: item["evidence_id"] for item in visible}
    from .goals import goal_constraints

    context = {
        "goal": goal,
        "goal_constraints": goal_constraints(goal),
        "history": [{"tool": item["tool"]} for item in history],
        "evidence": [
            {
                "evidence_id": forward[item["evidence_id"]],
                "text": item["text"][:600],
                "start_ms": item["start_ms"],
                "end_ms": item["end_ms"],
            }
            for item in visible
        ],
    }
    if budget is not None:
        context["budget"] = budget
    for item in reversed(history):
        if item["tool"] == "search_course_evidence":
            context["practice_kind"] = item["result"].get("practice_kind", "auto")
            if item["result"].get("concept_evidence_ids"):
                context["concept_evidence_ids"] = [
                    forward[ref] for ref in item["result"]["concept_evidence_ids"] if ref in selected
                ]
            break
    for item in history:
        if item["result"].get("linear_request"):
            from .linear import effective_linear_request

            context["linear_request"] = effective_linear_request(item["result"]["linear_request"])
            break
    if context.get("practice_kind") == "python_strings":
        from .strings import novel_string_input

        context["new_input_option"] = novel_string_input(goal, evidence)
    from .method_scope import latest_coverage

    coverage = latest_coverage(history)
    if coverage is not None:
        context["course_coverage"] = aliases_in(
            visible_references(
                decision_observation({"course_coverage": coverage})["course_coverage"], selected
            ),
            forward,
        )
    if history and "example_check" in history[-1]["result"]:
        context["example_check"] = aliases_in(history[-1]["result"]["example_check"], forward)
    if history and "quality" in history[-1]["result"]:
        context["quality"] = aliases_in(repair_observation(history[-1]["result"]["quality"]), forward)
    # Keep the learner's requirements after source/context observations as well.
    context["goal"] = context.pop("goal")
    context["goal_constraints"] = context.pop("goal_constraints")
    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": compact_json(
                {"goal": goal, "previous_turns": previous_turns, "history": [], "evidence": []}
                if previous_turns
                else {"goal": goal, "history": [], "evidence": []}
            ),
        },
    ]
    for index, item in enumerate(history):
        call_id = f"c{index}"
        wire_arguments = dict(item["arguments"])
        if wire_arguments.get("linear_request"):
            from .linear import effective_linear_request

            wire_arguments["linear_request"] = effective_linear_request(wire_arguments["linear_request"])
        if item["result"].get("program_plan") is not None:
            wire_arguments.pop("program", None)
            if not wire_arguments.get("explanation"):
                wire_arguments.pop("explanation", None)
            wire_arguments["program_plan"] = item["result"]["program_plan"]
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": item["tool"],
                            "arguments": compact_json(
                                aliases_in(visible_references(wire_arguments, selected), forward)
                            ),
                        },
                    }
                ],
            }
        )
        result = (
            context
            if index == len(history) - 1
            else aliases_in(visible_references(decision_observation(item["result"]), selected), forward)
        )
        messages.append({"role": "tool", "tool_call_id": call_id, "content": compact_json(result)})
    return messages, reverse


def complete_citation_context(draft, evidence, read_window):
    """Complete at most two cut-off cited sentences, never beyond eight passages.

    Caller supplies an authorized, version-fenced window reader. No unrelated
    window hit becomes a citation, and required original sources cannot be evicted.
    """
    refs = list(
        dict.fromkeys(
            ref
            for field in [draft["questions"][1], draft, draft["questions"][0]]
            for ref in field["evidence_ids"]
        )
    )
    pool = [item for item in evidence if item["evidence_id"] in refs]
    windows = []
    for ref in refs:
        if len(pool) >= 8 or len(windows) >= 2:
            break
        last = next(item for item in pool if item["evidence_id"] == ref)
        if last.get("source_type") not in {"SUBTITLE", "SUBTITLE_TRANSLATION"} or not unfinished_speech(last):
            continue
        # Follow already-present contiguous speech first; only read a missing tail.
        while unfinished_speech(last):
            following = next(
                (
                    item
                    for item in pool
                    if item.get("source_type") == last["source_type"]
                    and 0 <= item["start_ms"] - last["end_ms"] <= 3000
                    and item["end_ms"] > last["end_ms"]
                ),
                None,
            )
            if following is None:
                break
            last = following
        if not unfinished_speech(last) or last["evidence_id"] in windows:
            continue
        windows.append(last["evidence_id"])
        window = sorted(read_window(last["evidence_id"]), key=lambda item: (item["start_ms"], item["end_ms"]))
        for item in window:
            if len(pool) >= 8:
                break
            if (
                item.get("source_type") == last["source_type"]
                and 0 <= item["start_ms"] - last["end_ms"] <= 3000
                and item["end_ms"] > last["end_ms"]
            ):
                if item["evidence_id"] not in {source["evidence_id"] for source in pool}:
                    pool.append(item)
                last = item
                if not unfinished_speech(last):
                    break
    return pool, windows


def adjacent_anchor_context(evidence, anchor, window, time_scope):
    """Fill at most two free slots with immediate same-track source neighbors.

    The reader must authorize the whole window first. No source is evicted and
    existing explicit time bounds still apply. This supplies context, not support.
    """
    result = list(evidence)
    present = {item["evidence_id"] for item in result}
    neighbors = [
        item
        for item in window
        if item["evidence_id"] not in present
        and item.get("source_type") == anchor.get("source_type")
        and (
            0 <= anchor["start_ms"] - item["end_ms"] <= 3000
            or 0 <= item["start_ms"] - anchor["end_ms"] <= 3000
        )
        and (
            time_scope.get("start_ms") is None
            or (item["end_ms"] >= time_scope["start_ms"] and item["start_ms"] <= time_scope["end_ms"])
        )
    ]
    for item in sorted(
        neighbors,
        key=lambda value: (
            value["start_ms"] > anchor["start_ms"],
            abs(value["start_ms"] - anchor["start_ms"]),
        ),
    )[:2]:
        if len(result) >= 8:
            break
        if item["evidence_id"] not in present:
            result.append(item)
            present.add(item["evidence_id"])
    return result


def course_order(evidence):
    """Present timed observations in course order without changing their IDs.

    Ranking chooses the bounded source set. This only orders that set for reading;
    no adjacency or support is inferred. Legacy untimed observations stay ordered.
    """
    if not all(type(item.get("start_ms")) is int and type(item.get("end_ms")) is int for item in evidence):
        return list(evidence)
    return sorted(evidence, key=lambda item: (item["start_ms"], item["end_ms"]))
