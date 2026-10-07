"""Session-scoped facts derived only from committed, supported atomic checks.

Canonicalization is deliberately syntactic. It preserves scope and fails closed
on unresolved subjects; it never predicts entailment or supplies new evidence.
"""

import re
from collections import Counter
from typing import Annotated, Literal

from pydantic import Field

from ..contracts import Contract
from .atomic import AtomicAssessment, atomic_claims
from .atomic_delta import SUPPORT_POLICY, AtomicBasis, claim_fingerprint, digest
from .strengthening import strengthening_guards

VERSION = "atomic_ledger_v7"
SCOPE = ("owner_id", "course_id", "revision", "session_id")
_DISCOURSE = re.compile(r"^(?:(?:但是|然而|但|而|并且|以及)|(?:but|however|and)\b)\s*", re.I)
_PRONOUN = re.compile(r"^(?:它|其|it\b)\s*", re.I)
_UNRESOLVED = re.compile(
    r"它|它们|他|她|他们|其|该|这个|那个|这种|那种|这样|那样|另一个|二者|前者|后者|这里|那里|这(?:些|一点)|那(?:些|一点)|此(?:过程|关系|方法)|\b(?:it|its|he|she|his|her|they|them|their|this|that|these|those|another|former|latter)\b",
    re.I,
)
_LITERAL = r"""(?:"[^"\n]{1,80}"|'[^'\n]{1,80}')"""
_OBJECT = re.compile(
    rf"(?:原来的|原来|原|旧的|旧|新的|新)?\s*{_LITERAL}\s*(?:字符串)?对象"
    rf"|(?:原来的|原|旧的|旧|新的|新)?(?:字符串)?对象\s*{_LITERAL}"
)
_DEPENDENT_SCOPE = re.compile(
    r"如果|除非|只有|因为|由于|之后|之前|^(?:当|取|再取|令)|若(?:令|设)?|假设|此时|与.+相比"
    r"|(?:时|后|前)[，,]?$|\b(?:if|unless|because|when|before|after|let|suppose|assuming)\b",
    re.I,
)
_VARIABLE = re.compile(r"变量\s*[A-Za-z_]\w*")
_EXECUTION_TIME = re.compile(
    r"^(?:随后)?执行\s+[A-Za-z_]\w*\s*=\s*['\"][^'\"]+['\"]\s*(?:时|后)[，,]?$", re.I
)
_REMAINING_OBJECT = re.compile(
    rf"^(?:而是|而)?\s*(?:{_OBJECT.pattern})?\s*(?:仍然|仍)?(?:保留|存在)?在内存中$", re.I
)
_REBIND_ACTIVE = re.compile(r"^(?:并)?将\s*(?:变量\s*)?([A-Za-z_]\w*)\s*重新绑定到\s*(.+)$")
_REBIND_PASSIVE = re.compile(r"^变量\s*([A-Za-z_]\w*)\s*被重新绑定到\s*(.+)$")
_UNBIND = re.compile(r"^(?:Python\s*)?解除\s*(?:变量\s*)?([A-Za-z_]\w*)\s*与\s*(.+)\s*的绑定$")
_INTRA_REBIND = re.compile(
    rf"^(?:而是|而)?(?:Python\s*)?创建(?:了)?\s*"
    rf"(?P<object>(?:一个)?(?:全)?(?:{_OBJECT.pattern}))"
    r"\s*并(?:且)?\s*将\s*(?:变量\s*)?(?P<variable>[A-Za-z_]\w*)"
    r"\s*重新绑定到\s*(?P<pronoun>它)$"
)
_CREATED_OBJECT = re.compile(
    rf"^(?:而是|而)?(?:Python\s*)?创建(?:了)?\s*"
    rf"(?P<object>(?:一个)?(?:全)?(?:{_OBJECT.pattern}))$"
)
_OBJECT_POINTER = re.compile(r"^(?:它|(?:这个|该)(?:新)?(?:字符串)?对象)$")


class Fact(Contract):
    fact_id: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    normalized_claim: Annotated[str, Field(min_length=1, max_length=3000)]
    claim_type: Literal["assertion", "qualification"]
    text: Annotated[str, Field(min_length=1, max_length=3000)]
    owner_id: int
    course_id: str
    revision: int
    session_id: str
    source_run_id: str
    verifier_version: Literal["atomic_ledger_v7"] = VERSION
    evidence_ids: Annotated[list[str], Field(min_length=1, max_length=8)]
    evidence_hashes: dict[str, str]
    evidence_spans: dict[str, dict]
    source_answer: Annotated[str, Field(min_length=1, max_length=1500)]
    source_claim: AtomicAssessment
    # Only supported units may supply subject/comparator identity. Raw answer
    # context remains audit provenance, never canonical fact content.
    source_units: Annotated[list[AtomicAssessment], Field(min_length=1, max_length=24)]


def object_name(value):
    literal = re.search(_LITERAL, value)
    if not literal:
        return value
    # Quote style/noun order is surface syntax; old/new identity is retained.
    age = (
        "原来的 "
        if re.search(r"原|旧", value[: literal.start()])
        else "新的 "
        if "新" in value[: literal.start()]
        else ""
    )
    noun = "字符串对象" if "字符串" in value[: literal.start()] + value[literal.end() :] else "对象"
    return age + '"' + literal[0][1:-1] + '" ' + noun


def canonical_claim(claim, answer=None, *, supported_units=None, binding_units=None):
    original = claim["source_text"].strip()
    # Speech attribution is not composed by this syntactic ledger. Preserve
    # quoted targets in Atomic review/revision reuse, without publishing their
    # interior clauses as unqualified independent facts.
    if answer is not None and any(
        match.start() < claim["end"] and claim["start"] < match.end()
        for match in re.finditer(r"“[^”]*”|‘[^’]*’", answer)
    ):
        return None
    # A dangling cause/condition/time modifier has no independently bound
    # consequent. Keep it in final model verification, not the fact ledger.
    if claim["claim_type"] == "qualification" and not _DISCOURSE.match(original):
        return None
    if original.endswith(("?", "？")) or re.search(r"(?:时|后|前)[，,]?$", original):
        return None
    text = _DISCOURSE.sub("", original).strip().strip("。；，.!?;,！？ \n")
    if len(text) < 2 or not re.search(r"\w", text) or text.startswith(("(", "（")):
        return None
    if re.match(
        r"^(?:对于|对(?!数)|在|于|从|自|通过|借助|利用|经由|若|如果|当|假设|设|取)"
        r"|^(?:from|with|under|by|using|via|through|in|on|at)\b",
        text,
        re.I,
    ):
        # A preposition/condition can be verified in the whole answer, but
        # without its consequent it is not an independently reusable fact.
        return None
    if original.startswith(("而是", "而非")):
        # A contrastive predicate inherits a subject from the preceding
        # clause. Keep its exact verification, without inventing that binding.
        return None
    if re.match(
        r"^(?:恰好是|仅需|所需的|将|接着|然后|随后|非|根据(?!课程)|需要|判断|强调了|与.+相比|并|共|继续|最终|随着|总工作量|总时间复杂度|当|取|再取|令|注意|从)",
        text,
    ):
        # A bare starting point such as "从 n 不断除以 2" is not the
        # independently scoped result or endpoint of the taught process.
        return None
    if re.match(r"^from\b", text, re.I):
        return None
    if re.fullmatch(r".+通过(?:每次|不断|反复).+(?:减半|缩小|比较|检查)", text):
        # An instrumental phrase names how an unstated consequent occurs.
        # Its subject alone does not turn the missing result into a fact.
        return None
    # These pieces name a location/topic or inherit a subject/antecedent. An
    # exact supported span is not automatically an independently reusable fact.
    # Keep its judgment for revision reuse, but never fill in its predicate or
    # silently generalize a conditional formula in the generation ledger.
    if re.match(
        r"^(?:即|等于|再加上|的(?:时间|空间|工作量|复杂度)|则|此时|两者|体现|并在|(?:实际上|其实|事实上)?就是)",
        text,
    ):
        return None
    if re.match(r"^(?:这|那|此)", text):
        return None
    if re.fullmatch(r"(?:例如|比如|如|在|于).+(?:中|内|里)", text):
        return None
    if re.fullmatch(r"(?:在|于).+(?:下|上)|(?:in|on|at)\s+.+(?:scale|perspective|coordinates?)", text, re.I):
        return None
    if re.match(r"^(?:通过|借助|利用|经由)|^(?:by|using|via|through)\s+", text, re.I):
        # An instrumental premise asserts no result by itself. Keep the exact
        # unit in Atomic review and delta reuse, not as a detached course fact.
        return None
    if re.fullmatch(
        r"(?:对|对于).+(?:来说|而言)|(?:as for|regarding|concerning)\s+.+", text, re.I
    ) or re.match(r"^(?:对|对于).{1,80}(?:来说|而言)[，,。.]?", claim["context_text"]):
        # A topic has no predicate. Atomic support in a containing sentence
        # does not make that fragment an independently reusable assertion.
        return None
    if re.match(r"^(?:考虑|选取|选择|设定|给定|consider\b|choose\b|take\b|given\b)", text, re.I):
        # Hypothetical inputs are answer scaffolding, not established course
        # facts. Their derived relationship remains in full answer review.
        return None
    endpoint = r"直到|持续到|\buntil\b"
    if (
        re.search(endpoint, claim["context_text"], re.I)
        and not re.search(endpoint, text, re.I)
        and re.search(r"持续|重复|循环|\b(?:continues?|repeats?)\b", text, re.I)
    ):
        # A repetition predicate needs its stopping bound. Dropping a rejected
        # lifetime qualifier from a separate present-state assertion remains
        # safe; it does not establish an unbounded repetition.
        return None
    # Runtime measurements depend on the measured input. This ledger cannot
    # compose a size qualifier from another sentence/parenthesis; require that
    # the independently stored measurement itself binds its input size.
    duration = re.search(
        r"(?:\d+(?:\.\d+)?|[一二三四五六七八九十百]+)\s*(?:秒|毫秒|seconds?|secs?\b|milliseconds?)",
        text,
        re.I,
    )
    if (
        duration
        and re.search(r"算法|运行|执行|耗时|algorithm|runtime|takes?", text, re.I)
        and not re.search(r"输入|规模|\b(?:n|m|size)\s*(?:=|≈|is)\s*\d", text, re.I)
    ):
        return None
    representative = re.search(
        r"(?:Θ|θ|theta)\s*\([^)]*\)\s*对应.{0,24}(?:尺度|规模|值)\s*(?:是|为|=)\s*\d"
        r"|(?:线性|对数|指数)(?:增长)?尺度\s*(?:是|为|=)\s*\d"
        r"|\b(?:linear|logarithmic|exponential)\s+scale\s*(?:is|=)\s*\d",
        text,
        re.I,
    )
    if representative and not re.search(
        r"\b(?:n|m|k|size)\s*(?:=|≈|为|取|is)\s*\d|输入(?:规模)?\s*(?:为|是|=|≈)\s*\d", text, re.I
    ):
        # An example's numeric scale is true only for its chosen input. A
        # reviewed neighbouring condition cannot become an unbound fact.
        return None
    # Quoted speech can be supported as an attributed utterance while its
    # detached clause cannot be reused as an unconditional course fact. Bare
    # reporting predicates likewise contain no independently reusable content.
    if text.startswith(("”", "“", "’", "‘")) or text.endswith(("”", "’")):
        return None
    if re.fullmatch(
        r"(?:并|还)?(?:课程|老师|教师|教授|讲者|他|她)?(?:还|也|又)?(?:进一步|接着|随后|继续)?(?:说|说明|强调|指出|提到|解释(?:说)?|总结)",
        text,
    ):
        return None
    if re.fullmatch(
        r"(?:课程|老师|教师|教授|讲者)(?:说|指出|提到|说明)[，,]?\s*对于.+(?:问题|情况|主题)", text
    ):
        return None
    if re.search(r"(?:算法|方法)$", text) or re.fullmatch(r"(?:课程|课文|讲座|材料)中", text):
        return None
    if re.match(r"^(?:具体来说[，,]?\s*)?(?:若|假设|let\b|suppose\b)", text, re.I):
        return None
    if re.match(r"^(?:时|时候|情况下|条件下)", text):
        # A remainder of a removed time/condition has no bound antecedent.
        return None
    context_units = atomic_claims(claim["context_text"])
    other_units = [c for c in context_units if c["source_text"].strip() != original]
    # Do not turn a contingent predicate into an unconditional ledger fact.
    # This ledger does not compose factual clauses; unresolved scope stays in
    # atomic review rather than being copied or silently removed.
    if any(_DEPENDENT_SCOPE.search(c["source_text"]) for c in other_units):
        return None
    units = atomic_claims(answer or claim["context_text"])
    if answer is None:
        units = [
            {**u, "start": u["start"] + claim["context_start"], "end": u["end"] + claim["context_start"]}
            for u in units
        ]
    if supported_units is not None and any(
        u.get("supported") is not True
        or u.get("model_supported") is not True
        or u.get("strengthening_guards")
        for u in supported_units
    ):
        return None
    prefix_units = [u for u in units if claim["context_start"] <= u["start"] and u["end"] <= claim["start"]]

    def names(pattern, values, transform=lambda x: x):
        found = {}
        for unit in values:
            for match in pattern.finditer(unit["source_text"]):
                found.setdefault(transform(match[0]), []).append(unit)
        return found

    def bind(found):
        if len(found) != 1:
            return None
        key, sources = next(iter(found.items()))
        if supported_units is not None:
            positive = {u["id"]: u for u in supported_units}
            if any(
                u["id"] not in positive or any(positive[u["id"]][k] != v for k, v in u.items())
                for u in sources
            ):
                return None
            sources = [positive[u["id"]] for u in sources]
        if binding_units is not None:
            binding_units.extend(sources)
        return key

    subjects = names(_OBJECT, prefix_units, object_name)
    if _PRONOUN.match(text):
        subject = bind(subjects)
        if subject is None:
            return None
        text = _PRONOUN.sub(subject, text, count=1)
    elif re.match(r"^与.+(?:不同|相同|相等|一致)", text):
        subject = bind(subjects)
        if subject is None:
            return None
        text = subject + text
    elif re.match(r"^(?:不再被|不再通过|仍然存在|仍存在|(?:只是|只)?无法(?:再)?)", text):
        subject = bind(subjects)
        if subject is None:
            return None
        text = subject + text
    elif re.match(r"^(?:并)?(?:重新绑定|不再引用|不再指向)", text):
        variable = bind(names(_VARIABLE, prefix_units))
        if variable is None:
            return None
        text = variable + re.sub(r"^并", "", text)
    if text.endswith("它"):
        subject = bind(subjects)
        if subject is None:
            return None
        text = text[:-1] + subject
    if _UNRESOLVED.search(text):
        return None
    if claim["start"] > claim["context_start"] and not (_OBJECT.match(text) or _VARIABLE.match(text)):
        # Split clauses may be entailed in their containing statement without
        # establishing an independent subject. Only the explicitly bound
        # identity relations above are composed; do not guess an algorithm,
        # comparator or result subject from neighbouring prose.
        return None
    text = _OBJECT.sub(lambda m: object_name(m[0]), text)
    # A named reference relation has the same subject/object under active and
    # passive syntax. No modality, negation, quantity or lifetime is stripped.
    obj = r"(?:原来的 |新的 )?\"[^\"\n]{1,80}\" (?:字符串)?对象"
    passive = re.fullmatch(rf"({obj})不再被变量\s*([A-Za-z_][A-Za-z0-9_]*)\s*引用", text)
    active = re.fullmatch(rf"变量\s*([A-Za-z_][A-Za-z0-9_]*)\s*不再(?:引用|指向)\s*({obj})", text)
    if passive:
        text = f"变量 {passive[2]}不再引用{passive[1]}"
    elif active:
        text = f"变量 {active[1]}不再引用{active[2]}"
    comparison = re.fullmatch(rf"({obj})是一个完全不同的对象", text)
    if comparison:
        objects = names(_OBJECT, units, object_name)
        if len(objects) != 2 or comparison[1] not in objects:
            return None
        other = next(v for v in objects if v != comparison[1])
        if bind({other: objects[other]}) is None:
            return None
        text = "与".join(sorted([comparison[1], other])) + "不同"
    # Synonyms for an unspecified location do not add duration or universality.
    text = re.sub(r"仍(?:然)?存在于([\w]+)中(?:的某个(?:地方|位置))?", r"仍存在于\1中", text)
    normalized = " ".join(text.split())
    # A removed connective does not turn an assertion into a modifier. No
    # factual predicate is ever supplied from another unit or parent sentence.
    kind = "assertion" if _DISCOURSE.match(original) else claim["claim_type"]
    return normalized, kind, text


def context_bound_projection(claim, answer, supported_units, binding_units=None):
    """Project a named state relation with its verified subject and scope.

    Syntax from the answer can veto a projection, never supply its content.
    Execution times stay explicit. Other premises require the complete verified
    prefix, preserving conditions/causes rather than silently generalizing them.
    """
    if not supported_units:
        return None
    try:
        verified = {
            unit["id"]: AtomicAssessment.model_validate(unit).model_dump() for unit in supported_units
        }
        spans = {unit["id"]: unit for unit in atomic_claims(answer)}
    except (KeyError, ValueError, TypeError):
        return None
    if len(verified) != len(supported_units) or any(
        not unit["supported"]
        or unit["model_supported"] is not True
        or unit["strengthening_guards"]
        or unit["id"] not in spans
        or any(unit[key] != value for key, value in spans[unit["id"]].items())
        for unit in verified.values()
    ):
        return None
    target = verified.get(claim["id"])
    if target is None or any(target[key] != value for key, value in claim.items()):
        return None
    context = [
        unit
        for unit in spans.values()
        if unit["context_start"] == claim["context_start"] and unit["context_end"] == claim["context_end"]
    ]
    prefix = [unit for unit in context if unit["end"] <= claim["start"]]
    same = [verified[unit["id"]] for unit in prefix if unit["id"] in verified]
    selected = []
    scopes = [
        unit
        for unit in context
        if unit["id"] != target["id"] and _DEPENDENT_SCOPE.search(unit["source_text"])
    ]
    # Unknown/rejected premises and trailing scope cannot be detached from the
    # predicate. A positive verdict elsewhere in the sentence is no substitute.
    if any(unit["id"] not in verified or unit["start"] > target["start"] for unit in scopes):
        return None
    times = [unit for unit in same if _EXECUTION_TIME.fullmatch(unit["source_text"].strip())]
    if len(times) > 1:
        return None
    time = times[0] if times else None
    original = target["source_text"].strip().rstrip("。；，.!;,！ ")
    if "?" in original or "？" in original:
        return None
    obj = _OBJECT.search(original)
    projected_source = target["source_text"]
    if _REMAINING_OBJECT.fullmatch(original):
        if obj is None:
            subjects = [(unit, match) for unit in same for match in _OBJECT.finditer(unit["source_text"])]
            identities = {object_name(match[0]) for _, match in subjects}
            if len(identities) != 1:
                return None
            subject = identities.pop()
            selected.extend(unit for unit, match in subjects if object_name(match[0]) == subject)
        else:
            subject = object_name(obj[0])
        predicate = original[obj.end() :] if obj else re.sub(r"^(?:而是|而)\s*", "", original)
        text = subject + predicate
    elif match := _UNBIND.fullmatch(original):
        obj = _OBJECT.fullmatch(match[2])
        if obj is None:
            return None
        text = f"变量 {match[1]}不再引用{object_name(obj[0])}"
    elif match := _REBIND_ACTIVE.fullmatch(original) or _REBIND_PASSIVE.fullmatch(original):
        object_phrase = match[2]
        if _OBJECT_POINTER.fullmatch(object_phrase):
            # Only the immediately preceding, fully verified creation can
            # bind this pointer. Raw spans locate/veto adjacency; their text
            # never supplies content. Shared evidence fences the relation to
            # compatible provenance within this answer/run.
            antecedent = verified.get(prefix[-1]["id"]) if prefix else None
            creation = (
                _CREATED_OBJECT.fullmatch(antecedent["source_text"].strip().rstrip("。；，.!;,！ "))
                if antecedent
                else None
            )
            noun = re.sub(_LITERAL, "", creation["object"]) if creation else ""
            if (
                not creation
                or antecedent["end"] != target["start"]
                or not set(antecedent["evidence_ids"]) & set(target["evidence_ids"])
                or ("新" in object_phrase and "新" not in noun)
                or ("字符串" in object_phrase and "字符串" not in noun)
            ):
                return None
            object_phrase = creation["object"]
            selected.append(antecedent)
            projected_source = original[: match.start(2)] + object_phrase
        else:
            obj = _OBJECT.search(object_phrase)
            if (
                obj is None
                or object_phrase[obj.end() :].strip()
                or not re.fullmatch(r"(?:一个)?(?:全)?", object_phrase[: obj.start()].strip())
            ):
                return None
        # Keep newness/type modifiers in the exact verified object phrase.
        text = f"变量 {match[1]}重新绑定到{object_phrase}"
    elif match := _INTRA_REBIND.fullmatch(original):
        # Both the created object and the rebinding predicate are in this one
        # fully supported exact span. Full-match syntax excludes competing
        # antecedents/modifiers; no neighbouring text supplies object identity.
        text = f"变量 {match['variable']}重新绑定到{match['object']}"
        projected_source = original[: match.start("pronoun")] + match["object"]
    else:
        # A parameterized mathematical statement is reusable only as its
        # complete verified sentence. Never detach numeric scales or rewrite
        # the formula, attribution, quotation, condition, or comparison.
        # Emit once, at the final unit; missing/rejected units veto the group.
        if (
            len(context) < 2
            or context[-1]["id"] != target["id"]
            or any(unit["id"] not in verified for unit in context)
        ):
            return None
        complete = [verified[unit["id"]] for unit in context]
        text = "".join(unit["source_text"] for unit in complete).strip().rstrip("。；.!;！ ")
        if (
            not re.search(r"\b[A-Za-z]\s*=\s*[0-9]", text)
            or not re.search(r"Θ|θ|\btheta\b|线性(?:规模|尺度)|对数(?:规模|尺度)", text, re.I)
            or not re.search(r"\blog|log[₂2]|对数", text, re.I)
            or _UNRESOLVED.search(text)
            or "?" in text
            or "？" in text
        ):
            return None
        if binding_units is not None:
            binding_units.extend(unit for unit in complete if unit["id"] != target["id"])
        return " ".join(text.split()), "assertion", text
    if any(unit["id"] not in {time["id"] for time in times} for unit in scopes):
        if any(unit["id"] not in verified for unit in prefix):
            return None
        selected = [verified[unit["id"]] for unit in prefix]
        text = (
            ("".join(unit["source_text"] for unit in selected) + projected_source)
            .strip()
            .rstrip("。；，.!;,！ ")
        )
    elif time:
        selected.append(time)
        text = time["source_text"].strip().rstrip("，,") + "，" + text
    if _UNRESOLVED.search(text) or any(
        match.start() < unit["end"] and unit["start"] < match.end()
        for unit in [target, *selected]
        for match in re.finditer(r"“[^”]*”|‘[^’]*’", answer)
    ):
        return None
    if binding_units is not None:
        binding_units.extend({unit["id"]: unit for unit in selected}.values())
    return " ".join(text.split()), "assertion", text


def span_view(item):
    return {k: item[k] for k in ("start_ms", "end_ms", "match_start", "match_end", "match_hash") if k in item}


def facts_from_review(scope, candidate, quality, evidence):
    if not quality.get("atomic_basis"):
        return []
    try:
        basis = AtomicBasis.model_validate(quality["atomic_basis"])
        assessments = [
            AtomicAssessment.model_validate(value) for value in quality.get("atomic_assessments", [])
        ]
    except (ValueError, KeyError, TypeError):
        return []
    if (
        basis.support_policy != SUPPORT_POLICY
        or basis.answer_sha256 != digest(candidate["explanation"])
        or set(basis.evidence_ids) != set(candidate["evidence_ids"])
        or len({e.evidence_id for e in basis.evidence}) != len(basis.evidence)
        or len({check.id for check in assessments}) != len(assessments)
    ):
        return []
    claims = atomic_claims(candidate["explanation"])
    by_id = {c["id"]: c for c in claims}
    available = {e["evidence_id"]: e for e in evidence}
    hashes = {e.evidence_id: e.text_sha256 for e in basis.evidence}
    supported_units = []
    for check in assessments:
        from .relation_support import validate_relation

        try:
            validate_relation(
                check.relation,
                check.model_dump(),
                check.evidence_ids,
                {k: e["text"][:1200] for k, e in available.items()},
                check.supported,
            )
        except ValueError:
            continue
        raw = check.model_dump()
        if (
            not check.supported
            or check.model_supported is not True
            or check.strengthening_guards
            or check.id not in by_id
            or any(raw[k] != v for k, v in by_id[check.id].items())
            or not set(check.evidence_ids) <= set(candidate["evidence_ids"]) & set(available) & set(hashes)
            or any(digest(available[r]["text"][:1200]) != hashes[r] for r in check.evidence_ids)
            or strengthening_guards(raw, [available[r]["text"][:1200] for r in check.evidence_ids])
        ):
            continue
        supported_units.append(raw)
    candidates = []
    for raw in supported_units:
        check = AtomicAssessment.model_validate(raw)
        bound = []
        canonical = canonical_claim(
            by_id[check.id], candidate["explanation"], supported_units=supported_units, binding_units=bound
        )
        if canonical is None:
            bound = []
            canonical = context_bound_projection(
                by_id[check.id], candidate["explanation"], supported_units, bound
            )
        if canonical is None:
            continue
        normalized, kind, text = canonical
        contributing = list({u["id"]: u for u in [raw, *bound]}.values())
        refs = sorted({r for u in contributing for r in u["evidence_ids"]})
        proof = dict(
            normalized_claim=normalized,
            claim_type=kind,
            text=text,
            **{k: scope[k] for k in SCOPE},
            source_run_id=scope["run_id"],
            evidence_ids=refs,
            evidence_hashes={ref: hashes[ref] for ref in refs},
            evidence_spans={ref: span_view(available[ref]) for ref in refs},
            source_answer=candidate["explanation"],
            source_claim=check,
            source_units=contributing,
        )
        identity = {
            k: proof[k]
            for k in (*SCOPE, "normalized_claim", "claim_type", "evidence_hashes", "evidence_spans")
        }
        candidates.append(Fact(fact_id=digest([VERSION, identity]), **proof).model_dump())
    counts = Counter((c["normalized_claim"], c["claim_type"]) for c in candidates)
    return [f for f in candidates if counts[(f["normalized_claim"], f["claim_type"])] == 1]


def valid_fact(value, scope):
    try:
        fact = Fact.model_validate(value)
        raw = fact.model_dump()
        if any(raw[k] != scope.get(k) for k in SCOPE):
            return None
        c = fact.source_claim
        extracted = {v["id"]: v for v in atomic_claims(fact.source_answer)}
        source = extracted.get(c.id)
        units = [u.model_dump() for u in fact.source_units]
        if (
            len({u["id"] for u in units}) != len(units)
            or c.model_dump() not in units
            or any(
                not u["supported"]
                or not u.get("relation")
                or u["model_supported"] is not True
                or u["strengthening_guards"]
                or u["id"] not in extracted
                or any(u[k] != v for k, v in extracted[u["id"]].items())
                for u in units
            )
        ):
            return None
        bound = []
        canonical = (
            canonical_claim(source, fact.source_answer, supported_units=units, binding_units=bound)
            if source
            else None
        )
        if canonical is None and source:
            bound = []
            canonical = context_bound_projection(source, fact.source_answer, units, bound)
        if (
            source is None
            or any(getattr(c, k) != v for k, v in source.items())
            or not c.supported
            or c.model_supported is not True
            or c.strengthening_guards
            or set(fact.evidence_ids) != {r for u in units for r in u["evidence_ids"]}
            or set(fact.evidence_hashes) != set(fact.evidence_ids)
            or set(fact.evidence_spans) != set(fact.evidence_ids)
            or canonical != (fact.normalized_claim, fact.claim_type, fact.text)
            or {u["id"] for u in units} != {c.id, *(u["id"] for u in bound)}
        ):
            return None
        identity = {
            k: raw[k] for k in (*SCOPE, "normalized_claim", "claim_type", "evidence_hashes", "evidence_spans")
        }
        if fact.fact_id != digest([VERSION, identity]):
            return None
        return fact
    except (ValueError, KeyError, TypeError, StopIteration):
        return None


def matching_facts(body):
    if body.get("relation_review") != SUPPORT_POLICY:
        return {}
    scope = body.get("ledger_scope", {})
    evidence = {e["evidence_id"]: e["text"] for e in body["evidence"]}
    allowed = set(body["candidate"]["evidence_ids"]) & set(evidence)
    bindings = body.get("ledger_evidence_bindings", {})
    aliases = body.get("ledger_aliases", {})
    matches = {}
    keys = [canonical_claim(c, body["candidate"]["explanation"]) for c in body["atomic_claims"]]
    counts = Counter(k[:2] for k in keys if k)
    for claim, key in zip(body["atomic_claims"], keys, strict=True):
        if key is None or counts[key[:2]] != 1:
            continue
        for value in body.get("ledger_facts", [])[:24]:
            fact = valid_fact(value, scope)
            refs = [aliases.get(r, r) for r in fact.evidence_ids] if fact else []
            if (
                fact is None
                or (fact.normalized_claim, fact.claim_type) != key[:2]
                or not set(refs) <= allowed
                or any(
                    digest(evidence[a]) != fact.evidence_hashes[r]
                    or bindings.get(r) != fact.evidence_spans[r]
                    for r, a in zip(fact.evidence_ids, refs, strict=True)
                )
                or strengthening_guards(claim, [evidence[r] for r in refs])
            ):
                continue
            from .relation_support import validate_relation

            try:
                for unit in fact.source_units:
                    validate_relation(
                        unit.relation,
                        unit.model_dump(),
                        unit.evidence_ids,
                        {r: evidence[a] for r, a in zip(fact.evidence_ids, refs, strict=True)},
                        True,
                    )
            except ValueError:
                continue
            matches[claim["id"]] = (
                AtomicAssessment(
                    **claim,
                    relation={
                        "source_relation": "mixed",
                        "claim_quote": claim["source_text"][:160],
                        "grounds": [
                            {
                                "evidence_id": a,
                                "quote": next(
                                    q.quote
                                    for u in fact.source_units
                                    for q in u.relation.grounds
                                    if q.evidence_id == r
                                ),
                            }
                            for r, a in zip(fact.evidence_ids, refs, strict=True)
                        ],
                    },
                    supported=True,
                    model_supported=True,
                    evidence_ids=refs,
                    fingerprint=claim_fingerprint(claim, body["candidate"]["evidence_ids"]),
                ),
                fact.fact_id,
            )
            break
    return matches


def generation_view(facts, evidence, aliases):
    available = {e["evidence_id"]: e for e in evidence}
    forward = {v: k for k, v in aliases.items()}
    result = []
    for value in facts:
        fact = valid_fact(value, value)
        if (
            fact is None
            or not set(fact.evidence_ids) <= set(available) & set(forward)
            or any(
                digest(available[r]["text"][:1200]) != fact.evidence_hashes[r]
                or span_view(available[r]) != fact.evidence_spans[r]
                for r in fact.evidence_ids
            )
            or any(
                strengthening_guards(u.model_dump(), [available[r]["text"][:1200] for r in u.evidence_ids])
                for u in fact.source_units
            )
        ):
            continue
        result.append(
            {
                "fact_id": fact.fact_id[:16],
                "text": fact.text,
                "claim_type": fact.claim_type,
                "evidence_ids": [forward[r] for r in fact.evidence_ids],
            }
        )
    return result[:12]
