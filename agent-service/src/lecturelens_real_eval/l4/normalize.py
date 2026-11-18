"""Turn each path's learner-visible output into one judge-ready form.

Citations are renumbered C1..Cn in first-appearance order and carry the authoritative Evidence text
(the same canonical text for every path, so support is judged against identical sources). Markdown
headings, emphasis markers and product field labels are removed; meaning is not rewritten.
"""

import re

# A 60-second caption segment is about 900 characters; the bound only stops pathological rows.
EVIDENCE_CHARS = 1500
HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
EMPHASIS = re.compile(r"(\*\*|__)(.+?)\1", re.DOTALL)
SPACE = re.compile(r"[ \t]+")
BLANK = re.compile(r"\n{3,}")


def clean(text, labels=()):
    text = HEADING.sub("", text or "")
    text = EMPHASIS.sub(r"\2", text)
    for label in labels:
        text = re.sub(rf"^\s*{re.escape(label)}\s*[:：]\s*", "", text, flags=re.MULTILINE)
    text = SPACE.sub(" ", text)
    return BLANK.sub("\n\n", text).strip()


def normalize(text, cited, evidence, *, inline=False, labels=()):
    """cited: evidence ids in the order the product reports them; evidence: {id: canonical text}."""
    order = []
    if inline:
        for match in re.finditer(r"\[([^\[\]\s]+)\]", text or ""):
            if match.group(1) in evidence and match.group(1) not in order:
                order.append(match.group(1))
    for evidence_id in cited:
        if evidence_id not in order:
            order.append(evidence_id)
    missing = [e for e in order if e not in evidence]
    if missing:
        raise KeyError(f"cited evidence not in the authoritative snapshot: {missing[:3]}")
    label = {evidence_id: f"C{n}" for n, evidence_id in enumerate(order, 1)}
    body = text or ""
    if inline:
        body = re.sub(
            r"\[([^\[\]\s]+)\]",
            lambda m: f"[{label[m.group(1)]}]" if m.group(1) in label else m.group(0),
            body,
        )
    return {
        "text": clean(body, labels),
        "citations": [{"cid": label[e], "text": evidence[e][:EVIDENCE_CHARS]} for e in order],
        "citation_scope": "inline" if inline else "response",
    }
