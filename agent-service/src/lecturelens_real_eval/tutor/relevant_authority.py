"""V15 offline retrieval observation; no embeddings or relevance-quality claim."""

import re

from lecturelens_real_eval.runner import SnapshotAuthority


def terms(text):
    words = set(re.findall(r"[a-z]{2,}", text.casefold()))
    for phrase in re.findall(r"[\u3400-\u9fff]+", text):
        words.update(phrase[i : i + 2] for i in range(len(phrase) - 1))
    return words


class RelevantSnapshotAuthority(SnapshotAuthority):
    def read(self, scope, action="CHECK", **args):
        if action != "SEARCH":
            return super().read(scope, action, **args)
        query = terms(args["query"])
        ranked = [(len(query & terms(e["text"])), i, e) for i, e in enumerate(self.rows(scope))]
        selected = [e for score, _, e in sorted(ranked, key=lambda row: (-row[0], row[1])) if score > 0][:8]
        return {
            **{k: scope[k] for k in ("owner_id", "course_id", "revision")},
            "evidence": [
                {k: e[k] for k in ("evidence_id", "text", "start_ms", "end_ms", "source_type")}
                for e in selected
            ],
            "retrieval_observation": {"positive_matches": len(selected), "no_hit": not selected},
        }
