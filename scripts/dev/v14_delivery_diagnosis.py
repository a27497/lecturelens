"""Read retained v14 artifacts; no provider client, credentials or behavior changes."""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / ".data/tutor-v14-live-20261107"
RUN = RAW / "v14-frozen16-once"
BASE = ROOT / "eval/tutor-v14-fresh-v1"
MARKER = re.compile(r"\[([0-9a-f]{64})\]")


def read(path):
    return json.loads(path.read_text())


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def retained_frames():
    """Associate all proposals with calls, preserving ignored parallel proposals."""
    frames = []
    for row in lines(RUN / "turns.jsonl"):
        proposals = iter(row.get("proposals", []))
        for call in row.get("calls", []):
            first = next(proposals)
            group = [first] + [next(proposals) for _ in range(first["dropped_tool_calls"])]
            sequence = len(frames) + 1
            wire = RUN / f"wire/{sequence:03d}-request.json"
            assert digest(wire) == call["request_sha256"]
            frames.append(dict(sequence=sequence, turn_key=row["turn_key"], call=call, proposals=group))
        assert next(proposals, None) is None
    return frames


def context(sequence):
    wire = read(RUN / f"wire/{sequence:03d}-request.json")
    return wire, json.loads(wire["messages"][-1]["content"])


def citation_cost(text):
    ids = MARKER.findall(text)
    unique = list(dict.fromkeys(ids))
    return dict(
        chars=len(text),
        utf8_bytes=len(text.encode()),
        json_string_chars=len(json.dumps(text, ensure_ascii=False)),
        citation_occurrences=len(ids),
        distinct_citations=len(unique),
        citation_chars=sum(len(m.group()) for m in MARKER.finditer(text)),
        noncitation_chars=len(MARKER.sub("", text)),
        repeated_marker_chars=(len(ids) - len(unique)) * 66,
    )


def analyze():
    manifest = read(RAW / "artifact-manifest.json")
    assert all(digest(RAW / p) == h for p, h in manifest["files"].items())
    rows = lines(RUN / "turns.jsonl")
    by_key = {r["turn_key"]: r for r in rows}
    frames = retained_frames()
    history_checks = []
    for frame in frames:
        row = by_key[frame["turn_key"]]
        _, body = context(frame["sequence"])
        previous = [
            r
            for r in rows
            if r["dialogue_id"] == row["dialogue_id"]
            and r["ordinal"] < row["ordinal"]
            and r["status"] == "completed"
        ][-6:]
        expected_history = [
            {k: r[k] for k in ("ordinal", "learner_text", "answer", "evaluation", "outcome")}
            for r in previous
        ]
        assert body["history"] == expected_history
        history_checks.append(
            dict(wire_sequence=frame["sequence"], turn_key=row["turn_key"], exact_actual_history=True)
        )
    failures = []
    for row in rows:
        if row["status"] != "failed":
            continue
        finishes = [
            f
            for f in frames
            if f["turn_key"] == row["turn_key"] and f["proposals"][0]["name"] == "finish_tutor_turn"
        ]
        assert len(finishes) == 2
        initial, repair = finishes
        before_wire, before = context(initial["sequence"])
        after_wire, after = context(repair["sequence"])
        args = initial["proposals"][0]["arguments"]
        assert after["rejected_finish"] == {k: args.get(k, "") for k in ("outcome", "text", "evaluation")}
        assert after["history"] == before["history"]
        assert after["summary"] == before["summary"]
        observation = after["observations"][-1]
        kept = observation["keep_ids"]
        original = {e["evidence_id"]: e for e in before["evidence"]}
        assert after["evidence"] == [original[eid] for eid in kept]
        assert observation["size_violations"] == {"text": {"actual": len(args["text"]), "limit": 1600}}
        assert observation["remove_ids"] == []
        lengths = []
        for frame, wire, body in [(initial, before_wire, before), (repair, after_wire, after)]:
            assert wire["max_tokens"] == 1200
            finish = next(
                t["function"] for t in wire["tools"] if t["function"]["name"] == "finish_tutor_turn"
            )
            assert finish["parameters"]["properties"]["text"]["maxLength"] == 1600
            assert "Target text ≤1200" in wire["messages"][0]["content"]
            assert "hard limit of 1600 characters" in wire["messages"][0]["content"]
            lengths.append(
                dict(
                    wire_sequence=frame["sequence"],
                    **citation_cost(frame["proposals"][0]["arguments"]["text"]),
                    completion_tokens=frame["call"]["usage"]["completion_tokens"],
                    max_output_tokens=wire["max_tokens"],
                    history_ordinals=[h["ordinal"] for h in body["history"]],
                    history_answer_chars=sum(len(h["answer"] or "") for h in body["history"]),
                    summary_chars=len(body["summary"]),
                    evidence_ids=[e["evidence_id"] for e in body["evidence"]],
                    system_chars=len(wire["messages"][0]["content"]),
                    user_json_chars=len(wire["messages"][-1]["content"]),
                    runtime_proxy=len(
                        json.dumps([wire["messages"], wire["tools"]], ensure_ascii=False).encode()
                    )
                    + 1200,
                )
            )
        failures.append(
            dict(
                turn_key=row["turn_key"],
                initial=lengths[0],
                repair=lengths[1],
                exact_rejected_finish=True,
                history_and_summary_unchanged=True,
                exact_kept_evidence=True,
                observation=observation,
                turn_reserved_proxy=row["reserved_tokens"],
                final_error=row["error_code"],
                published_answer=row["answer"],
            )
        )
    _, excel = context(29)
    sentence = "When opening your CSV file in Excel again, it will parse it as follows:"
    matching = [e for e in excel["evidence"] if sentence in e["text"]]
    assert len(matching) == 1
    target = by_key["v14-sheets-lineends:2"]
    assert matching[0]["evidence_id"] in [e["evidence_id"] for e in target["citations"]]
    refusals = [
        {
            "turn_key": r["turn_key"],
            "status": r["status"],
            "answer": r["answer"],
            "root_failure": r.get("root_failure"),
        }
        for r in rows
        if r["script"]["expected_insufficient"]
    ]
    contextual = [
        {"turn_key": r["turn_key"], "status": r["status"], "root_failure": r.get("root_failure")}
        for r in rows
        if r["script"]["context_followup"]
    ]
    annotation = read(RAW / "codex-source-review.json")
    required = [
        (k, c) for k, label in annotation["labels"].items() for c in label["claims"] if c["requires_citation"]
    ]
    pairs = [(k, pair) for k, label in annotation["labels"].items() for pair in label["citation_checks"]]
    direct = {(k, p["claim_id"]) for k, p in pairs if p["label"] == "supported"}
    covered = direct | {
        (k, c["claim_id"])
        for k, c in required
        if c["local_cited_premise_claims"] and all((k, p) in direct for p in c["local_cited_premise_claims"])
    }
    for k, label in annotation["labels"].items():
        for claim in label["claims"]:
            start, end = claim["answer_offsets"]
            assert by_key[k]["answer"][start:end] == claim["text"]
        for pair in label["citation_checks"]:
            assert any(
                e["evidence_id"] == pair["evidence_id"] and e["text"] == pair["observed_quote"]
                for e in by_key[k]["citations"]
            )
    return dict(
        prior_manifest_verified_files=len(manifest["files"]),
        statuses=dict(Counter(r["status"] for r in rows)),
        attempted=sum(bool(r.get("turn_id")) for r in rows),
        retained_model_calls=len(frames),
        actual_history_checks=history_checks,
        failures=failures,
        excel=dict(
            question=excel["learner_text"],
            source_sentence=sentence,
            source_lines=[76, 78],
            search_wire_sequence=28,
            finish_wire_sequence=29,
            observed_id=matching[0]["evidence_id"],
            evidence_in_context=True,
            evidence_cited=True,
            answer_chars=len(target["answer"]),
            unused_hard_char_capacity=1600 - len(target["answer"]),
            explicit_excel_reopening_request=False,
            frozen_reference_requires_reopening=True,
            omission_cause="UNVERIFIED_MODEL_CONTENT_SELECTION; reference demands a specific corroborating fact not explicitly named by learner",
        ),
        refusal_positions=refusals,
        context_positions=contextual,
        citation_annotation_arithmetic=dict(
            explicit_pairs=len(pairs),
            supported_pairs=sum(p["label"] == "supported" for _, p in pairs),
            requiring_claims=len(required),
            direct_supported=sum((k, c["claim_id"]) in direct for k, c in required),
            frozen_supported=sum((k, c["claim_id"]) in covered for k, c in required),
        ),
        real_requests=0,
        embedding_calls=0,
        reviewer_calls=0,
        cost_usd="0",
        raw_http_response_bytes_available=False,
        replay_scope="Retained parsed tool proposals/usage; reconstructed HTTP envelopes, exact original request bytes asserted",
    )
