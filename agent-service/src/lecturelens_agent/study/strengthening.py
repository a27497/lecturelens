"""Conservative negative signals for scope/modality/lifetime strengthening.

Domain-specific missing premises can reject a stronger claim. Generic scope
is judged semantically: a definition can quantify without saying "every".
Presence of a word never proves the actual subject/relation.
"""

import re

_SIGNALS = {
    "universal_scope": re.compile(
        r"\b(?:all|every|each|always|never)\b|所有|全部|任何|每个|每一|一切|始终|从不", re.I
    ),
    # Unrelated "all" in a passage (e.g. "expand all terms") cannot license
    # scanning every input element from an asymptotic bound alone.
    "exhaustive_scan": re.compile(
        r"(?:每个|每一|所有|全部)(?:的)?\s*(?:输入)?\s*(?:[A-Za-z]\s*个?\s*)?元素|遍历(?:整个|全部)"
        r"|线性遍历|\blinearly\s+(?:scan\w*|travers\w*)\b"
        r"|逐(?:个|一)(?:检查|遍历|访问)(?:输入|数组|元素)|(?:输入|数组).{0,8}逐(?:个|一)(?:检查|遍历|访问)"
        r"|\b(?:all|every|each)\s+(?:input\s+)?(?:[A-Za-z]\s+)?(?:elements?|items?)\b",
        re.I,
    ),
    "universal_negative": re.compile(
        r"\b(?:none|nothing|nobody|no\s+(?!longer\b)\w+)\b|没有(?:任何|一个|其他|其它)?(?:变量|主体|对象|人|引用)|无任何|未被引用|不被引用|无引用|独立|完全孤立|彻底孤立|孤立对象|完全无关|毫无(?:关联|关系)|\b(?:completely\s+)?isolated\b|\bunreferenced\b|\bindependent\b|\b(?:completely|entirely)\s+unrelated\b",
        re.I,
    ),
    "certainty": re.compile(
        r"\b(?:will|must|definitely|inevitably)\b|\bgoing\s*to\b|一定|必然|必定|将会|最终会", re.I
    ),
    "duration": re.compile(r"\b(?:until|forever|permanently)\b|直到|永久|永远|一直持续", re.I),
    "immutability": re.compile(
        r"不可变|不能(?:被)?修改|不可(?:被)?修改|\bimmutable\b|\b(?:cannot|can't)\s+be\s+(?:modified|changed)\b",
        re.I,
    ),
    "garbage_collection": re.compile(
        r"垃圾回收|\b(?:garbage[ -]collect\w*|GC)\b|\breclaim\w*\s+(?:the\s+)?memory\b", re.I
    ),
    "input_mutation_policy": re.compile(
        r"(?:原(?:始)?(?:数组|输入)|数组|输入数据).{0,12}(?:不(?:会|被)?|没有|未被).{0,4}(?:修改|改变|删除)"
        r"|不(?:会)?修改(?:原(?:始)?)?(?:数组|输入)"
        r"|(?:不再|不会再|没有再|无须再).{0,24}(?:修改|改变|删除)"
        r"|\b(?:no|without|not)\s+(?:any\s+)?further\s+(?:modification|mutation|changes?)\b"
        r"|\b(?:original\s+)?(?:array|input)\b.{0,25}\b(?:unchanged|unmodified|not modified|not changed|not deleted)\b",
        re.I,
    ),
    "derivation_attribution": re.compile(
        r"(?:课程|老师|教师|教授).{0,12}(?:通过|用|使用).{0,12}(?:代入|替换|重新参数化)"
        r"|\b(?:course|instructor|lecturer|teacher)\b.{0,25}\b(?:substitut\w*|reparametriz\w*)\b",
        re.I,
    ),
    # Neighbour comparisons and size reduction do not identify a position,
    # branch-selection rule, or named algorithm. These are negative signals;
    # the presence of any term still does not prove the claimed operation.
    "position_specialization": re.compile(
        r"中间元素|中点元素|中间位置|中位元素|\b(?:middle|midpoint|central)\s+(?:element|item|position)\b",
        re.I,
    ),
    "branch_specialization": re.compile(
        r"左半|右半|更大(?:的)?邻居|较大(?:的)?邻居|搜索方向|递归方向|递归分支|(?:确定|决定).{0,12}方向"
        r"|向(?:左|右)(?:.{0,4}一半|递归|搜索)"
        r"|(?:决定|确定|选择|判断).{0,12}(?:哪一半|一半|半边|半区|子数组)"
        r"|(?:选择|选取|确定|决定)[^。.!?]{0,80}(?:更大[^。.!?]{0,20}(?:侧|边|邻居)|(?:子数组|半边|一半)[^。.!?]{0,20}(?:递归|搜索|处理))"
        r"|\b(?:left|right)\s+half\b|\b(?:larger|greater)\s+(?:neighbou?r(?:ing)?|side)\b|\b(?:search|recursion|recursive)\s+(?:direction|branch)\b"
        r"|\b(?:choose|chooses|decide|decides|determine|determines|select|selects)\b.{0,25}\b(?:which|half|subarray)\b",
        re.I,
    ),
    "predicate_definition": re.compile(
        r"(?:大于等于|大于|≥|>).{0,20}(?:邻居|相邻)"
        r"|\b(?:greater than|at least as large as)\b.{0,25}\bneighbou?rs?\b",
        re.I,
    ),
    "branch_condition_specialization": re.compile(
        r"(?:包含|含有|保证有).{0,12}峰值.{0,8}(?:一半|半边)"
        r"|\bhalf\b.{0,30}\b(?:contains?|containing)\b.{0,20}\bpeak\b",
        re.I,
    ),
    "existence_specialization": re.compile(
        r"是否存在.{0,12}(?:峰值|目标|解|匹配)|\bwhether\b.{0,12}\b(?:there\s+is|exists?)\b", re.I
    ),
    "subject_specialization": re.compile(
        r"(?:左右邻居|相邻元素|邻居)(?:是否|是|为|构成).{0,5}峰值"
        r"|\b(?:neighbou?rs?|adjacent\s+elements?)\s+(?:are|is|form)\s+(?:a\s+)?peak\b",
        re.I,
    ),
    "predicate_condition_specialization": re.compile(
        r"(?:若|如果).{0,12}(?:未找到|没有找到|未发现|没有发现|不是|不为|不构成).{0,8}(?:峰值|目标|匹配)"
        r"|(?:若|如果)(?:它|其|该元素)?不是[，,；;]"
        r"|\bif\b.{0,20}\b(?:not found|not a peak|no match|no target)\b",
        re.I,
    ),
    "single_element_base": re.compile(
        r"(?:单(?:个)?|一(?:个)?|唯一)(?:的)?元素|(?:规模|长度)\s*(?:为|是|=)?\s*1\b"
        r"|\b(?:one|single)[ -]element\b|\bsize\s*(?:is|of|=)?\s*1\b",
        re.I,
    ),
    "asymptotic_value": re.compile(
        r"(?:Θ|θ|theta)\s*\([^()]{1,48}\)\s*(?:的(?:规模|值|数值)|对应的规模|growth\s+scale|value)?\s*"
        r"(?:=|≈|等于|是|为|对应(?:的是|于|是)?|equals?|is|corresponds?\s+to)\s*"
        r"(?:\d+(?:\s*(?:\^|\*\*)\s*[A-Za-z0-9]+|[⁰-⁹ᵏⁿ]+)?|[A-Za-z](?:\s*(?:\^|\*\*)\s*\d+|[⁰-⁹]+)?)"
        r"(?=\s*(?:[,，。.；;!?！？]|$))",
        re.I,
    ),
    "subproblem_merge": re.compile(
        r"合并|\b(?:merge|merging)\b"
        r"|\b(?:combine|combining)\b.{0,30}\b(?:solutions?|subproblems?)\b",
        re.I,
    ),
    "recursive_fanout": re.compile(
        r"递归.{0,12}(?:求解|解决|处理).{0,4}(?:每个|各个|所有|两个|多个)子问题"
        r"|\brecurs\w*\b.{0,30}\b(?:each|every|all|both|multiple)\b.{0,20}\bsubproblems?\b",
        re.I,
    ),
    "exponential_speedup": re.compile(
        r"指数.{0,8}(?:效率|性能|提升|加速)|(?:效率|性能|加速).{0,8}指数"
        r"|\bexponential\b.{0,15}\b(?:speedup|acceleration|improvement)\b",
        re.I,
    ),
    "algorithm_specialization": re.compile(
        r"二分查找|二分搜索|快速排序|归并排序|堆排序|\b(?:binary\s+search|quicksort|merge\s*sort|heapsort)\b",
        re.I,
    ),
}

# A stated endpoint may be described as reaching a stopping case rather than
# with the target's word "until". This only removes a lexical negative signal;
# atomic review must still establish the actual endpoint and consequence.
_ENDPOINT = re.compile(r"到达|达到|持续到|\b(?:reach|reaches|reaching|eventually|up to)\b", re.I)

_COUNTS = re.compile(
    r"(?P<cn>\d+|[一二两三四五六七八九十]+)\s*(?:次|个)\s*(?P<unit>操作|运算|比较)"
    r"|\b(?P<en>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?P<engunit>operations?|comparisons?)\b",
    re.I,
)
_NUMBERS = {
    **dict(zip("一二两三四五六七八九十", [1, 2, 2, 3, 4, 5, 6, 7, 8, 9, 10], strict=True)),
    **dict(zip("one two three four five six seven eight nine ten".split(), range(1, 11), strict=True)),
}

_SYMBOLIC_COUNTS = re.compile(
    r"(?:log[₂₃₄₅₆₇₈₉0-9]*\s*\(?[A-Za-z]\)?|[A-Za-z](?:\s*\^\s*\w+)?|\d+\s*\^\s*[A-Za-z])"
    r"\s*次\s*(?:操作|运算|比较)"
    r"|\b(?:log\d*\s*\(?[A-Za-z]\)?|[A-Za-z](?:\^\w+)?)\s+(?:operations?|comparisons?)\b",
    re.I,
)

_MEASURED_INPUT = re.compile(
    r"\b(?:n|m|size)\s*(?:=|为|是|等于|取|being|is)\s*(?:\d+(?:[,.]\d+)?\s*(?:万|千|亿|million|thousand)?|[零一二三四五六七八九十百千万亿]+)",
    re.I,
)
_APPROX_INPUT = re.compile(
    r"\b(?:n|m|size)\b.{0,25}(?:约|大约|左右|上下|附近|roughly|approximately|about|around|or so)"
    r"|\b(?:n|m|size)\b.{0,12}(?:about|around|roughly|approximately)\s*\d",
    re.I,
)
_APPROX_WORD = re.compile(r"约|大约|左右|上下|附近|roughly|approximately|about|around|or so|≈", re.I)
_MEASURED_CONTEXT = re.compile(
    r"耗时|秒|实际运行|测试结果|运行时间|\b(?:runtime|seconds?|timing|benchmark|takes?)\b", re.I
)
_POSSIBLE_COUNT = re.compile(
    r"(?:potentially|possibly|at most|up to|可能(?:的)?|最多|至多).{0,35}"
    r"(?:\d+|[一二两三四五六七八九十]|one|two|three|four).{0,12}(?:次)?\s*(?:比较|comparisons?)",
    re.I,
)
_DEFINITE_PER_STEP_COUNT = re.compile(
    r"(?:每(?:一步|次|层)|each|every|always).{0,60}"
    r"(?:\d+|[一二两三四五六七八九十]|one|two|three|four).{0,8}(?:次)?\s*(?:比较|comparisons?)",
    re.I,
)
_COUNT_HEDGE = re.compile(r"可能|最多|至多|大约|约|potentially|possibly|at most|up to|about", re.I)


def operation_counts(text):
    result = set()
    for match in _COUNTS.finditer(text):
        raw = (match["cn"] or match["en"]).lower()
        number = int(raw) if raw.isdigit() else _NUMBERS.get(raw)
        unit = match["unit"] or match["engunit"].lower()
        if number is not None:
            result.add(
                (number, "comparison" if unit == "比较" or unit.startswith("comparison") else "operation")
            )
    return result


def derivation_action_observed(sources):
    return any(
        re.search(
            r"代入|替换|重新参数化|(?:令|设)\s*[A-Za-z]|\b(?:let|substitut\w*|reparametriz\w*)\b", text, re.I
        )
        for text in sources
    )


def strengthening_guards(claim, sources):
    # Scope is read from the exact target. A containing claim's supported
    # subject must not erase a target's independent quantifier or modality.
    target = claim["source_text"]
    guards = [
        name
        for name, pattern in _SIGNALS.items()
        if name != "universal_scope"
        and pattern.search(target)
        and not any(
            pattern.search(text) or (name == "duration" and _ENDPOINT.search(text)) for text in sources
        )
    ]
    # A directional selection can be split into individually plausible atomic
    # fragments ("choose a neighbour" / "the larger side" / "recurse there").
    # Reject each fragment covered by the unsourced composite relation before
    # it can be reused by delta review or published as a detached Ledger fact.
    if "branch_specialization" not in guards and not any(
        _SIGNALS["branch_specialization"].search(source) for source in sources
    ):
        start = claim["start"] - claim["context_start"]
        end = claim["end"] - claim["context_start"]
        if any(
            match.start() < end and start < match.end()
            for match in _SIGNALS["branch_specialization"].finditer(claim["context_text"])
        ):
            guards.append("branch_specialization")
    if "derivation_attribution" in guards and derivation_action_observed(sources):
        guards.remove("derivation_attribution")
    # A growth class has no pointwise scalar value. Neither a hypothetical
    # row nor a source's informal notation can establish that type equality.
    if _SIGNALS["asymptotic_value"].search(target) and "asymptotic_value" not in guards:
        guards.append("asymptotic_value")
    # A numeric asymptotic scale or example row does not certify a number of
    # actual operations, even when phrased approximately. Missing quantities
    # can reject; present quantities still require full scoped model support.
    observed_counts = set().union(*(operation_counts(source) for source in sources))
    if operation_counts(target) - observed_counts:
        guards.append("numeric_operation_count")

    def symbolic(text):
        return {re.sub(r"\s", "", m[0]).lower() for m in _SYMBOLIC_COUNTS.finditer(text)}

    if symbolic(target) - set().union(*(symbolic(source) for source in sources)):
        guards.append("symbolic_operation_count")
    if (
        _DEFINITE_PER_STEP_COUNT.search(target)
        and not _COUNT_HEDGE.search(target)
        and any(_POSSIBLE_COUNT.search(source) for source in sources)
    ):
        guards.append("count_modality")
    if (
        _MEASURED_INPUT.search(target)
        and _MEASURED_CONTEXT.search(claim["context_text"])
        and not _APPROX_WORD.search(target)
        and any(_APPROX_INPUT.search(source) for source in sources)
    ):
        guards.append("input_precision")
    return guards
