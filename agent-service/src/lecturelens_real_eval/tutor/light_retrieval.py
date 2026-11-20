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
    r"\b(?:compar(?:e[ds]?|ing|ison)|difference|differ(?:s|ent)?|contrast|versus|vs\.?|unlike)\b"
    r"|区别|比较|对比|不同|异同",
    re.IGNORECASE,
)
_EN_PAIR = re.compile(
    r"\b(?:differ(?:s|ent)?\s+from|compare[ds]?\s+(?:with|to)|and|with|versus|vs\.?)\b",
    re.IGNORECASE,
)
_ZH_PAIR = re.compile(r"与|和|及|跟|、")
_EN_EDGE = re.compile(
    r"^(?:how (?:do|does|did|is|are)\s+|what (?:is|are)\s+(?:the\s+)?difference\s+between\s+"
    r"|(?:please\s+)?compare\s+|(?:the\s+)?difference\s+between\s+)"
    r"|\s+(?:differs?|compares?)\b[?!. ]*$",
    re.IGNORECASE,
)
_ZH_EDGE = re.compile(r"^(?:请)?(?:比较|对比)|(?:在[^，,？?]{1,45})?有(?:何|什么)?(?:区别|不同|异同).*$")
_PARTS = re.compile(
    r"(?:[,;]\s*(?:and\s+)?|\s+and\s+)(?=(?:why|how|what|does|do|did|which|where|when)\b)"
    r"|[?？;；]\s*(?=\S)|[，,；;](?=(?:那么|以及|又|并且|这|它|为什么|如何|是否))",
    re.IGNORECASE,
)
_QUESTION = re.compile(
    r"\b(?:why|how|what|does|do|did|which|where|when)\b|为什么|如何|是否|什么", re.IGNORECASE
)


def _query(text):
    # Java validates UTF-16 units. Avoid splitting a surrogate pair at the bound.
    return text.encode("utf-16-le")[: 2 * QUERY_CHARS].decode("utf-16-le", errors="ignore").strip()


def targeted_queries(question):
    """Retain the whole question and, when detectable, focus on its distinct requests."""
    full = _query(question)
    # Split independent interrogatives before looking for two comparands.
    pieces = [
        part.strip(" ,，:：.。?？")
        for part in _PARTS.split(full)
        if (_QUESTION.search(part) or _COMPARE.search(part)) and len(part) > 8
    ]
    if len(pieces) >= 2:
        return list(dict.fromkeys([full, *pieces[: MAX_QUERIES - 1]]))

    if _COMPARE.search(full):
        segment = re.split(r"[?？;；]", full)[0]
        if _ZH_PAIR.search(segment):
            parts = _ZH_PAIR.split(_ZH_EDGE.sub("", segment), maxsplit=1)
            prefix, separator, left = parts[0].rpartition("，")
            if separator and len(parts) == 2:
                parts = [left, f"{prefix}，{parts[1]}"]
        else:
            parts = _EN_PAIR.split(_EN_EDGE.sub("", segment), maxsplit=1)
        if len(parts) == 2:
            cleaned = [part.strip(" ,，:：.。?？") for part in parts]
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
    authority, scope, question, history, *, simple="HYBRID_8_NEIGHBORS", complex_="HYBRID_16", route=True
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
