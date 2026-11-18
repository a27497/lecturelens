"""Blind judge packets, the separate path mapping, the reveal join and the agreement sample.

The judge sees one normalized response per entry with no path, repetition, cost or timing. The
mapping that joins anonymous response ids back to (path, rep, item) is written to a different file
and bound to the packet by its sha256; the reveal refuses a packet, mapping or decision set that
does not match exactly.
"""

import hashlib
import json
import math
import random
import re
from collections import defaultdict

ID = re.compile(r"^r[0-9a-f]{12}$")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha256(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def gold_view(item):
    """The gold fields the judge may see. Category and split stay hidden."""
    if item["answerable"]:
        return {
            "answerable": True,
            "nuggets": [
                {
                    "id": n["id"],
                    "importance": n["importance"],
                    "text": n["text"],
                    "caption_anchor": [c["quote"] for c in n["cues"]],
                }
                for n in item["nuggets"]
            ],
            "must_not_claim": item.get("must_not_claim", []),
        }
    return {"answerable": False, "rationale": item["rationale"]}


def build(responses, items, *, seed):
    """responses: [{path, rep, item_id, text, citations: [{cid, text}], citation_scope, abstained}], status ok only."""
    rng = random.Random(seed)
    by_id = {item["item_id"]: item for item in items}
    entries, mapping = [], {}
    for response in sorted(responses, key=lambda r: (r["item_id"], r["path"], r["rep"])):
        while True:
            rid = "r" + "".join(rng.choice("0123456789abcdef") for _ in range(12))
            if rid not in mapping:
                break
        item = by_id[response["item_id"]]
        mapping[rid] = {"path": response["path"], "rep": response["rep"], "item_id": response["item_id"]}
        entries.append(
            {
                "response_id": rid,
                "question": item["question"],
                "language": item["language"],
                "gold": gold_view(item),
                "response": {
                    "text": response["text"],
                    "citations": response["citations"],
                    "citation_scope": response["citation_scope"],
                    "declared_insufficient_evidence": bool(response["abstained"]),
                },
            }
        )
    rng.shuffle(entries)
    packet = {"version": "l4-judge-packet-v2", "entries": entries}
    return packet, {"packet_sha256": sha256(packet), "responses": mapping}


def reveal(packet, mapping, decisions):
    """Join decisions back to (path, rep, item). decisions: {response_id: decision dict}."""
    if mapping["packet_sha256"] != sha256(packet):
        raise ValueError("REVEAL_PACKET_MISMATCH")
    ids = [entry["response_id"] for entry in packet["entries"]]
    if len(set(ids)) != len(ids) or set(ids) != set(mapping["responses"]):
        raise ValueError("REVEAL_MAPPING_MISMATCH")
    if set(decisions) != set(ids):
        missing, extra = set(ids) - set(decisions), set(decisions) - set(ids)
        raise ValueError(f"REVEAL_DECISIONS_INCOMPLETE missing={len(missing)} extra={len(extra)}")
    return [
        {**mapping["responses"][rid], "response_id": rid, "decision": decisions[rid]} for rid in sorted(ids)
    ]


def agreement_sample(packet, mapping, decisions, *, seed, fraction=0.2):
    """Seeded sample stratified by path; returns (review packet without path or verdict, judge-only key)."""
    rng = random.Random(seed)
    by_path = defaultdict(list)
    for rid, where in sorted(mapping["responses"].items()):
        by_path[where["path"]].append(rid)
    chosen = []
    for path in sorted(by_path):
        pool = by_path[path]
        chosen += rng.sample(pool, max(1, math.ceil(len(pool) * fraction)))
    chosen = sorted(chosen)
    entries = {entry["response_id"]: entry for entry in packet["entries"]}
    review = {
        "version": "l4-agreement-packet-v1",
        "seed": seed,
        "fraction": fraction,
        "entries": [entries[rid] for rid in chosen],
    }
    rng.shuffle(review["entries"])
    key = {
        "packet_sha256": sha256(review),
        "judge": {rid: decisions[rid] for rid in chosen},
        "paths": {rid: mapping["responses"][rid] for rid in chosen},
    }
    return review, key


def check_ids(decisions):
    bad = [rid for rid in decisions if not ID.match(rid)]
    if bad:
        raise ValueError(f"invalid response ids: {bad[:3]}")
