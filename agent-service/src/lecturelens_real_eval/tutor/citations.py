"""Citation syntax shared by the Tutor runtime and its evaluation adapter."""

import re

# extract_corpus.py emits v2-{course}-l{lecture}-p{page:02d}-e{ordinal:02d}.
# build_cases.py appends -zh for translated source variants.
# CourseEvidenceService emits lowercase SHA-256; study/context.py emits e{index+1}.
# Syntax only identifies candidates: selected evidence and authority still decide validity.
EVIDENCE_ID = re.compile(
    r"(?:v2-[a-z]+-l[1-9][0-9]*-p[0-9]{2,}-e[0-9]{2,}(?:-zh)?|[0-9a-f]{64}|e[1-9][0-9]*)"
)


def inline_citation_ids(text):
    return [token for token in re.findall(r"\[([^\[\]\n]+)\]", text) if EVIDENCE_ID.fullmatch(token)]


def assembled_citation_ids(text, evaluation=""):
    """Retain every candidate, once, in text then evaluation appearance order."""
    return list(dict.fromkeys(inline_citation_ids(text) + inline_citation_ids(evaluation)))
