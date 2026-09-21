"""Bounded conceptual scaffolding, still subject to course-evidence review."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..contracts import Contract


def string_concept(concept, language):
    zh = language == "zh"
    explanation = (
        "字符串不可变：不能通过索引赋值原地更改其字符，这样的操作会发生错误。"
        "重新绑定变量使它指向另一个字符串，并不修改原字符串。"
        if zh
        else "Strings are immutable: assigning to a character by index cannot change a string in place and gives an error. "
        "Rebinding a variable makes it refer to another string without modifying the original string."
    )
    if concept["skill"] == "immutability":
        question = (
            "为什么不能通过索引赋值原地更改字符串中的字符？"
            if zh
            else "Why can't assignment to a character by index change a string in place?"
        )
        points = (
            ["字符串对象创建后内容不可原地修改。", "索引赋值试图修改该对象，因此会发生错误。"]
            if zh
            else [
                "A string object's contents cannot be modified in place after creation.",
                "Index assignment attempts to modify that object, so it gives an error.",
            ]
        )
    else:
        question = (
            "变量重新绑定到另一个字符串，为什么不违反字符串不可变性？"
            if zh
            else "Why does rebinding a variable to another string not violate string immutability?"
        )
        points = (
            ["重新绑定改变变量引用的对象。", "原字符串的内容没有被修改。"]
            if zh
            else [
                "Rebinding changes which object the variable refers to.",
                "The original string's contents are not modified.",
            ]
        )
    return explanation, {
        "question": question,
        "answer_points": points,
        "evidence_ids": concept["evidence_ids"],
    }


def copied_string_input(goal, program, evidence):
    """Conservative duplication signal for an explicitly new string exercise.

    This does not certify novelty or course support. A changed input still needs
    computed output and semantic review. No keyword-specific example is encoded.
    """
    import ast
    import re

    if not re.search(
        r"(?:新|新的|不同的)字符串|(?:new|different|fresh)\s+strings?\b",
        goal,
        re.I,
    ):
        return False
    try:
        tree = ast.parse(program)
    except (ValueError, SyntaxError):
        return False
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value.strip()) > 1
    ]
    source = " ".join(item["text"] for item in evidence).casefold()
    return bool(literals) and all(value.casefold() in source for value in literals)


def novel_string_input(seed, evidence):
    """A bounded, replayable new literal suggestion; not a pedagogical proof."""
    import hashlib

    observed = "\n".join(item["text"] for item in evidence)
    for nonce in range(8):
        value = "sample_" + hashlib.sha256(f"{seed}:{nonce}".encode()).hexdigest()[:8]
        if value not in observed:
            return value
    return None


class StringRewrite(Contract):
    operation: Annotated[
        Literal["assign", "prefix_slice"],
        Field(
            description="assign renders s=value. prefix_slice renders s=value+s[start:]. Each item is ONE rebinding. Preserve requested operations; do not replace an expression by its computed literal output."
        ),
    ]
    value: Annotated[
        str,
        Field(
            max_length=40,
            description="For assign: the entire new literal. For prefix_slice: ONLY the prefix literal, not the whole result. No surrounding code quotes.",
        ),
    ]
    start: Annotated[int, Field(strict=True, ge=-40, le=40)] = 1

    @model_validator(mode="after")
    def literal_has_no_slice(self):
        if self.operation == "assign" and self.start != 1:
            raise ValueError("An assignment has no slice start")
        return self


class StringProgramPlan(Contract):
    variable: Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z_0-9]{0,15}$")] = "s"
    initial: Annotated[
        str,
        Field(
            max_length=40,
            description="Initial string content, no code quotes; preserve learner-specified text.",
        ),
    ]
    rebindings: Annotated[list[StringRewrite], Field(max_length=3)]
    print_positions: Annotated[
        list[Annotated[int, Field(strict=True, ge=0, le=3)]],
        Field(
            min_length=1,
            max_length=4,
            description="0 prints after initial assignment, 1 after first rebinding, etc. Strictly increasing; include every requested output.",
        ),
    ]

    @model_validator(mode="after")
    def executable_states(self):
        import keyword

        if keyword.iskeyword(self.variable) or self.variable == "print":
            raise ValueError("Reserved variable")
        if self.print_positions != sorted(set(self.print_positions)) or self.print_positions[-1] > len(
            self.rebindings
        ):
            raise ValueError("Print positions must name existing states in execution order")
        return self


def render_string_program(plan):
    plan = StringProgramPlan.model_validate(plan)
    var = plan.variable
    lines = [f"{var} = {plan.initial!r}"]
    if 0 in plan.print_positions:
        lines.append(f"print({var})")
    for index, change in enumerate(plan.rebindings, 1):
        expression = (
            repr(change.value)
            if change.operation == "assign"
            else f"{change.value!r} + {var}[{change.start}:]"
        )
        lines.append(f"{var} = {expression}")
        if index in plan.print_positions:
            lines.append(f"print({var})")
    return "\n".join(lines)
