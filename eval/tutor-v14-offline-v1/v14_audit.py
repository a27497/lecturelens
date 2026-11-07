"""Read-only reconciliation of retained v13 evidence; no provider/account access."""

import json
from decimal import Decimal

import v14_contract as C

RAW = C.ROOT / ".data/tutor-v13-resumed-20261107"


def read(path):
    return json.loads(path.read_text())


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def audit():
    C.verify_candidate()
    manifest = read(RAW / "artifact-manifest.json")
    assert len(manifest["files"]) == 487
    assert all(C.digest(RAW / p) == h for p, h in manifest["files"].items())
    run = RAW / "v13-new16-first"
    rows = {r["turn_key"]: r for r in lines(run / "turns.jsonl")}
    review = read(RAW / "codex-source-review.json")
    sources = {
        "carpentries-python": (C.ROOT / "eval/tutor-v13-grounding-v1/materials/carpentries-python-new.md")
        .read_text()
        .splitlines(),
        "carpentries-spreadsheets": (
            C.ROOT / "eval/tutor-v13-grounding-v1/materials/carpentries-spreadsheets-new.md"
        )
        .read_text()
        .splitlines(),
    }
    claims, pairs, inventory, derivations, full = [], [], [], [], []
    for key, label in review["labels"].items():
        row, seen = rows[key], {}
        source = sources[row["course_id"]]
        for claim in label["claims"]:
            a, b = claim["answer_offsets"]
            assert row["answer"][a:b] == claim["text"]
            for quote in claim["source_quotes"]:
                x, y = quote["lines"]
                assert quote["quote"] == "\n".join(source[x - 1 : y])
            seen[claim["claim_id"]] = claim
            claims.append((key, claim))
        for pair in label["citation_checks"]:
            evidence = next(e for e in row["citations"] if e["evidence_id"] == pair["evidence_id"])
            assert evidence["text"] == pair["observed_quote"]
            assert pair["evidence_id"] in seen[pair["claim_id"]]["citation_ids"]
            pairs.append((key, pair))
        required = [c for c in label["claims"] if c["requires_citation"]]
        covered = set()
        for claim in required:
            ps = [p for p in label["citation_checks"] if p["claim_id"] == claim["claim_id"]]
            direct = bool(ps) and all(p["label"] == "supported" for p in ps)
            premises = claim["local_cited_premise_claims"]
            derived = bool(premises) and all(
                seen[c]["citation_ids"]
                and all(p["label"] == "supported" for p in label["citation_checks"] if p["claim_id"] == c)
                for c in premises
            )
            if direct or derived:
                covered.add(claim["claim_id"])
            if derived:
                derivations.append(dict(turn_key=key, claim_id=claim["claim_id"], premises=premises))
            inventory.append(
                dict(
                    turn_key=key,
                    claim_id=claim["claim_id"],
                    direct_presence=bool(ps),
                    directly_supported=direct,
                    bounded_derivation=derived,
                    covered=direct or derived,
                    text=claim["text"],
                    source_ranges=[q["lines"] for q in claim["source_quotes"]],
                )
            )
        if (
            row["status"] == "completed"
            and not row["script"]["expected_insufficient"]
            and label["core_reference_complete"]
            and len(covered) == len(required)
        ):
            full.append(key)
    assert len(claims) == 45 and len(inventory) == 37 and len(pairs) == 38
    metrics = dict(
        explicit_pair_support=[sum(p["label"] == "supported" for _, p in pairs), len(pairs)],
        direct_citation_presence=[sum(c["direct_presence"] for c in inventory), len(inventory)],
        directly_supported_claims=[sum(c["directly_supported"] for c in inventory), len(inventory)],
        supported_claim_coverage=[sum(c["covered"] for c in inventory), len(inventory)],
        full_expected_answer_coverage=[len(full), 12],
    )
    assert metrics == dict(
        explicit_pair_support=[37, 38],
        direct_citation_presence=[34, 37],
        directly_supported_claims=[33, 37],
        supported_claim_coverage=[36, 37],
        full_expected_answer_coverage=[8, 12],
    )
    calls, events = lines(run / "calls.jsonl"), lines(run / "ledger.jsonl")
    usage = {
        k: sum(c["usage"][k] for c in calls)
        for k in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "prompt_cache_hit_tokens",
            "prompt_cache_miss_tokens",
        )
    }
    pricing = read(RAW / "pricing-observation.json")
    assert C.digest(RAW / "official-pricing.html") == pricing["source_sha256"]
    assert len(calls) == 34 and len(events) == 68
    exposure, settled, high, pending = 0, 0, 0, {}
    for event in events:
        if event["state"] == "reserved":
            assert event["reserved_nano_usd"] == event["input_bytes"] * 300 + 1200 * 1200
            pending[event["call_id"]] = event["reserved_nano_usd"]
            exposure += event["reserved_nano_usd"]
        else:
            assert event["state"] == "settled"
            value = event["usage"]["prompt_tokens"] * 300 + event["usage"]["completion_tokens"] * 1200
            assert event["charged_nano_usd"] == value
            exposure += value - pending.pop(event["call_id"])
            settled += value
        high = max(high, exposure)
        assert 0 <= exposure <= 700000000
    assert not pending and settled == exposure == 45606300 and high == 49290600
    for n, call in enumerate(calls, 1):
        assert call["status"] == "SUCCEEDED" and not call["anomalies"] and call["http_status"] == 200
        assert call["request_sha256"] == C.digest(run / f"wire/{n:03d}-request.json")
        reserve = next(
            e for e in events if e["call_id"] == call["ledger_call_id"] and e["state"] == "reserved"
        )
        assert reserve["wire_sha256"] == call["request_sha256"]
        assert (
            call["usage"]["prompt_cache_hit_tokens"] + call["usage"]["prompt_cache_miss_tokens"]
            == call["usage"]["prompt_tokens"]
        )
    cost = (
        usage["prompt_cache_hit_tokens"] * Decimal(pricing["input_cache_hit_offpeak"])
        + usage["prompt_cache_miss_tokens"] * Decimal(pricing["input_cache_miss_offpeak"])
        + usage["completion_tokens"] * Decimal(pricing["output_offpeak"])
    ) / Decimal(1000000)
    assert cost == Decimal("0.017591118")
    failed = next(r for r in rows.values() if r["status"] == "failed")
    oldrepair = json.loads(read(run / "wire/034-request.json")["messages"][-1]["content"])
    drafts = [p["arguments"]["text"] for p in failed["proposals"] if p["name"] == "finish_tutor_turn"]
    assert list(map(len, drafts)) == [1657, 1691]
    assert "rejected_finish" not in oldrepair and drafts[0] not in json.dumps(oldrepair, ensure_ascii=False)
    assert failed["error_code"] == "TUTOR_FINISH_FORMAT_INVALID" and failed["answer"] is None
    skips = [r for r in rows.values() if r["status"] == "SKIPPED"]
    assert len(skips) == 3 and all(r["root_failure"] == failed["turn_key"] for r in skips)
    return dict(
        historical_files_verified=487,
        historical_manifest_sha256=C.digest(RAW / "artifact-manifest.json"),
        review_type="CODEX_NONBLIND_SOURCE_REVIEW_NOT_INDEPENDENT_HUMAN",
        historical_labels_unchanged=True,
        counts=dict(
            expected=16, attempted=13, completed=12, failed=1, skipped=3, missing=0, scorable=12, scored=12
        ),
        correctness=dict(scheduled=[11, 16], completed=[11, 12]),
        citations=metrics,
        derivations=derivations,
        claim_inventory=inventory,
        full_supported_turns=full,
        unsupported_pairs=[dict(turn_key=k, **p) for k, p in pairs if p["label"] != "supported"],
        previous_costs=dict(
            requests=34,
            usage=usage,
            rate_calculated_usd=str(cost),
            local_ledger_usd="0.0456063",
            maximum_transient_exposure_usd="0.0492906",
            supplier_actual_bill="UNKNOWN_NOT_QUERIED",
            pricing=pricing,
        ),
        failure=dict(
            turn_key=failed["turn_key"],
            draft_lengths=list(map(len, drafts)),
            error_code=failed["error_code"],
            old_repair_has_draft=False,
            reserved_proxy=failed["reserved_tokens"],
            skip_keys=[r["turn_key"] for r in skips],
        ),
        this_stage=dict(real_model_requests=0, embeddings=0, reviewer=0, cost_usd="0"),
    )
