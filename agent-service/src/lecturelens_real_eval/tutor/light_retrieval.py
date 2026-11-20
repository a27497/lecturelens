"""Deterministic query planning and fusion for ordinary Light Tutor."""

import re
from collections import defaultdict

from lecturelens_agent.study.store import StudyError

# Shared with the existing Java query and READ budgets. A turn retains at most
# the former two-search evidence allowance, even after adding a third query.
QUERY_CHARS = 500
SEARCH_PAGE = 8
MAX_CONTEXT = 2 * SEARCH_PAGE
MAX_QUERIES = 3
RRF_K = 60

_COMPARE = re.compile(
    r"^(?:please\s+)?(?:compare|contrast)\b"
    r"|\b(?:differences? between|similarities between|versus|vs\.?)\b"
    r"|^(?:(?:explain|describe)\s+)?how\b.*\b(?:differ(?:s|ed|ent)?|compar(?:e[ds]?|able)|similar)\b"
    r"|^(?:请)?(?:比较|对比)|(?:有何|有什么|有|的|哪些)(?:区别|不同|异同|相同点)"
    r"|(?:如何|怎么)(?:比较|对比)",
    re.IGNORECASE,
)
_EN_PAIR = re.compile(
    r"\b(?:differ(?:s|ent)?\s+from|compare[ds]?\s+(?:with|to)|and|with|versus|vs\.?)\b",
    re.IGNORECASE,
)
_ZH_PAIR = re.compile(r"与|和|及|跟|、")
_EN_EDGE = re.compile(
    r"^(?:(?:(?:explain|describe)\s+)?how\s+(?:(?:do|does|did|is|are)\s+)?"
    r"|what (?:is|are)\s+(?:the\s+)?(?:differences?|similarities)\s+between\s+"
    r"|(?:please\s+)?(?:compare|contrast)\s+|(?:the\s+)?(?:differences?|similarities)\s+between\s+)"
    r"|\s+(?:differs?|compares?|similar)\b[?!. ]*$",
    re.IGNORECASE,
)
_ZH_EDGE = re.compile(
    r"^(?:请|如何|怎么)?(?:比较|对比)|(?:在[^，,？?]{1,45})?(?:有(?:何|什么)?|的)(?:区别|不同|异同|相同点).*$"
)
_PARTS = re.compile(
    r",?\s+and\s+(?=(?:why|how|what|does|do|did|which|where|when)\b)"
    r"|[?？;；]\s*(?=\S)|[，,；;](?=(?:那么|以及|又|并且|这|它|为什么|如何|是否))",
    re.IGNORECASE,
)
_SEGMENT = re.compile(
    r"(?<!\d)(?:\d{1,2}:)?\d{1,2}:\d{2}(?!\d)"
    r"|\b(?:opening|closing|first|second|earlier|later|final)\s+(?:section|segment|part|example)\b"
    r"|\b(?:early|earlier|later|at the (?:start|end))\s+(?:in|of)\s+(?:the\s+)?(?:lecture|video)\b"
    r"|(?:开头|结尾|前半|后半|第一|第二|前面|后面|稍早|稍后)\s*(?:段|部分|个例子)"
    r"|(?:课程|视频|讲座)(?:开头|结尾|前半段|后半段)",
    re.IGNORECASE,
)
_SEGMENT_BOUNDARY = re.compile(
    rf"(?:\s+(?:and|then)\s+|[,，]\s*)(?=(?:(?:at|in|from|the)\s+)*(?:{_SEGMENT.pattern}))",
    re.IGNORECASE,
)


def _query(text):
    # Java validates UTF-16 units. Avoid splitting a surrogate pair at the bound.
    return text.encode("utf-16-le")[: 2 * QUERY_CHARS].decode("utf-16-le", errors="ignore").strip()


def targeted_queries(question):
    """Keep the original query and probe identifiable comparands or distinct course excerpts."""
    full = _query(question)
    parts = _PARTS.split(full)
    # Punctuation only supplies boundaries after the question points to distinct course locations.
    focused = {}
    for part in (piece for clause in parts for piece in _SEGMENT_BOUNDARY.split(clause)):
        anchor = _SEGMENT.search(part)
        piece = part.strip(" ,，:：.。?？")
        if anchor and piece != anchor[0]:
            focused.setdefault(anchor[0].casefold(), piece)
    if len(focused) >= 2:
        return [full, *list(focused.values())[: MAX_QUERIES - 1]]

    for segment in parts:
        if not _COMPARE.search(segment):
            continue
        if _ZH_PAIR.search(segment):
            subjects = _ZH_PAIR.split(_ZH_EDGE.sub("", segment), maxsplit=1)
            prefix, separator, left = subjects[0].rpartition("，")
            if separator and len(subjects) == 2:
                subjects = [left, f"{prefix}，{subjects[1]}"]
        else:
            subjects = _EN_PAIR.split(_EN_EDGE.sub("", segment), maxsplit=1)
        if len(subjects) == 2:
            cleaned = [part.strip(" ,，:：.。?？") for part in subjects]
            if all(len(part) > 1 for part in cleaned):
                return list(dict.fromkeys([full, *cleaned]))

    return [full]


def fused_ids(searches, limit):
    scores = defaultdict(float)
    first_seen = {}
    for search_index, search in enumerate(searches):
        for rank, eid in enumerate(search["evidence_ids"], 1):
            scores[eid] += 1 / (RRF_K + rank)
            first_seen.setdefault(eid, (search_index, rank))
    return sorted(scores, key=lambda eid: (-scores[eid], first_seen[eid], eid))[:limit]


def retrieve_context(
    authority, scope, question, history, *, simple="HYBRID_8", complex_="HYBRID_16", route=True
):
    queries = targeted_queries(question) if route else [_query(question)]
    strategy = complex_ if len(queries) > 1 else simple
    # The dialogue still reaches generation verbatim. A follow-up also retains
    # the previous topic hint when targeted retrieval leaves room for it.
    if history and len(queries) < MAX_QUERIES:
        hint = history[0]["learner_text"][:250] + "\n" + history[-1]["learner_text"][:249]
        queries = list(dict.fromkeys([*queries, _query(hint)]))

    searches = []
    limit = SEARCH_PAGE if strategy in {"DENSE_8", "HYBRID_8", "MAIN"} else MAX_CONTEXT
    for query in queries:
        if strategy == "MAIN":
            rows = authority.read(scope, "SEARCH", query=query)["evidence"]
        else:
            rows = authority.read(scope, "TUTOR_SEARCH", query=query, tutor_strategy=strategy)["evidence"]
        ids = list(dict.fromkeys(row["evidence_id"] for row in rows))
        if len(rows) > limit:
            raise StudyError("TUTOR_EVIDENCE_LIMIT")
        searches.append({"query": query, "evidence_ids": ids})
    return fused_ids(searches, MAX_CONTEXT), searches
