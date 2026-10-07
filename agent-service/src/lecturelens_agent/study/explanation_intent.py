"""Narrow task-shape observations; never infer course support or an answer."""

import re


def concrete_actions(goal):
    return bool(
        re.search(
            r"具体|每一步|步骤|\b(?:concrete|steps?)\b|\bhow\b.{0,25}\b(?:work|execute|proceed)\b", goal, re.I
        )
    )


def omitted_comparison_operands(goal, answer, sources):
    # This is a negative completeness check, not an inferred procedure. If a
    # procedural answer itself mentions comparisons, source-named operands
    # cannot be replaced by a complexity bound or a count alone.
    comparison = re.compile(r"比较|\bcompar(?:e|es|ing|isons?)\b", re.I)
    sides = re.compile(r"左右|左.{0,24}右|\bleft\b.{0,60}\bright\b", re.I)
    neighbours = re.compile(r"邻居|相邻|\bneighbou?r(?:s|ing)?\b", re.I)
    taught = any(
        comparison.search(text) and (sides.search(text) or neighbours.search(text)) for text in sources
    )
    return bool(
        concrete_actions(goal)
        and taught
        and not (comparison.search(answer) and (sides.search(answer) or neighbours.search(answer)))
    )


def omitted_clarification_input_change(goal, answer, sources, semantic):
    raw = semantic.get("raw_question", goal)
    prior = semantic.get("previous_turns", [])
    method = re.compile(r"算法|方法|\b(?:algorithm|method)\b", re.I)
    selector = re.compile(r"第[一二三四五六七八九十\d]+(?:种|个)|\b(?:first|second|third)\b", re.I)
    whole_method = method.search(raw) or (
        selector.search(raw) and prior and method.search(prior[-1].get("explanation", ""))
    )
    # An explicit component question may properly focus on one operation.
    component = re.search(r"Θ\s*\(\s*1\s*\)|θ\s*1|常数项|常量项|constant (?:term|cost)", raw, re.I)
    reduction = re.compile(
        r"减半|缩小|减少.{0,12}(?:规模|输入)|一半.{0,8}(?:输入|子问题)|规模.{0,12}一半|\b(?:halv\w*|half[ -]size|reduce\w*)\b",
        re.I,
    )
    return bool(
        concrete_actions(raw)
        and whole_method
        and not component
        and any(reduction.search(text) for text in sources)
        and not reduction.search(answer)
    )


def scale_forms_observed(text):
    linear = re.search(
        r"\blinear\b|线性|(?:Θ|θ|theta)\s*\(\s*[A-Za-z]\s*\)"
        r"|(?:Θ|θ)\s*[A-Za-z](?![A-Za-z0-9_^²³ⁿ])|theta\s+[A-Za-z]\b(?!\s*[\^²³ⁿ])",
        text,
        re.I,
    )
    return bool(linear and re.search(r"log|对数", text, re.I))


def growth_scales_needed(goal, previous=()):
    # This helper computes only linear versus logarithmic scales. A request
    # for numeric clarification inherits that domain, never its old answer.
    relationship = bool(
        re.search(
            r"指数|增长.{0,8}(?:差|关系)|exponential|growth.{0,20}(?:gap|relationship|difference)", goal, re.I
        )
    )
    example = bool(re.search(r"例子|示例|\b(?:example|illustration)\b", goal, re.I))
    prior = previous[-1].get("explanation", "") if previous else ""
    return (relationship and scale_forms_observed(goal)) or (
        example and (scale_forms_observed(goal) or scale_forms_observed(prior))
    )
