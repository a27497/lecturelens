"""A run's learner intent, resolved once before observing new course material."""

from copy import deepcopy


def semantic_context(question, previous_turns):
    return {
        "raw_question": question,
        "resolved_goal": question,
        "previous_turns": deepcopy(previous_turns),
        "resolved": not previous_turns,
    }


def resolve_goal(context, goal):
    if context["resolved"]:
        return context
    if not isinstance(goal, str) or not goal.strip() or len(goal) > 1000:
        raise ValueError("Follow-up requires a standalone learning goal")
    return {**context, "resolved_goal": goal.strip(), "resolved": True}


def review_goal(context, kind):
    # The model's resolved goal guides tool choice, but it cannot add a
    # requirement to the learner's question during final answer review.
    # Previous turns remain visible to the reviewer to resolve referents.
    return (
        context["raw_question"]
        if kind == "explanation" and context["previous_turns"]
        else context["resolved_goal"]
    )
