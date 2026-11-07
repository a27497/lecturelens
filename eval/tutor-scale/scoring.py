"""Explicit denominators for citation annotation and binary rater agreement."""

from collections import Counter

LABELS = {"supported", "unsupported", "uncertain"}


def fraction(n, d):
    return dict(numerator=n, denominator=d, value=n / d if d else None)


def agreement(pairs):
    pairs = list(pairs)
    comparable = [
        (a, b) for a, b in pairs if a in ("supported", "unsupported") and b in ("supported", "unsupported")
    ]
    n = len(comparable)
    if not n:
        return dict(
            eligible=len(pairs),
            comparable=0,
            excluded=len(pairs),
            agreement=None,
            cohen_kappa=None,
            reason="NO_BINARY_PAIRS",
        )
    agree = sum(a == b for a, b in comparable) / n
    ca, cb = Counter(a for a, b in comparable), Counter(b for a, b in comparable)
    pe = sum(ca[k] * cb[k] for k in ("supported", "unsupported")) / n**2
    return dict(
        eligible=len(pairs),
        comparable=n,
        excluded=len(pairs) - n,
        agreement=agree,
        cohen_kappa=(agree - pe) / (1 - pe) if pe < 1 else None,
        reason="DEGENERATE_MARGINALS" if pe == 1 else None,
    )


def metrics(rows):
    """Rows are annotation units, never unverified model output judgments."""
    annotated = [r for r in rows if r.get("complete")]
    checks = [c for r in annotated for c in r["citation_checks"]]
    claims = [(r, c) for r in annotated for c in r["claims"] if c["requires_citation"]]
    supported = {
        (id(r), c["claim_id"]) for r in annotated for c in r["citation_checks"] if c["label"] == "supported"
    }
    with_ids = sum(bool(c["citation_ids"]) for r, c in claims)
    return dict(
        assigned_turns=len(rows),
        annotated_turns=len(annotated),
        missing_turns=len(rows) - len(annotated),
        citation_support_accuracy=fraction(sum(c["label"] == "supported" for c in checks), len(checks)),
        citation_presence_coverage=fraction(with_ids, len(claims)),
        supported_citation_coverage=fraction(
            sum((id(r), c["claim_id"]) in supported for r, c in claims), len(claims)
        ),
        uncertain_citation_pairs=sum(c["label"] == "uncertain" for c in checks),
        status="ANNOTATED" if annotated else "NOT_RUN",
    )
