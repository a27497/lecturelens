"""L4 benchmark campaign commands. Private state lives under --root (mode 0700), never in Git.

freeze    --audit FILE [--audit FILE]   write FREEZE.json after the gold audits (citation check included)
snapshot                                 save each lecture's authoritative Evidence
run       --split S --rep N [--paths]    one repetition, serial, resumable, never replaces a record
packet    --split S --label L [--reps]   build the blind judge packet and the separate mapping
judge     --split S --label L [--concurrency N]
                                         judge every packet entry (dev 4, holdout <= 8 in flight with a
                                         fallback to 4; <= 2 retries per entry)
verify    --split S --sources L1,L2,..   check per-repetition packets against the run records
score     --split S --label L [--sources L1,..]
                                         reveal, compute metrics, write summary.json
agreement --split S --label L [--sources L1,..] [--by-course]
                                         seeded 20% review packet(s) for independent reviewers
gate      --split S --done N --sources L1,..
                                         repetition cost gate: projected spend vs PLAN cost_gate_usd
balance   --split S                      provider balance precheck (>= 1.2 x estimated remaining spend)
rerun     --split S --rep N --units p:item,.. --reason R
                                         move failed records aside so `run` repeats those units once
rejudge   --split S --label L --ids r1,.. --reason R
                                         move decisions aside so `judge` repeats those entries once
ledger                                   print spend totals
"""

import argparse
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from . import blind, judge, pipeline, scoring
from .ledger import BudgetExceeded, Ledger
from .normalize import normalize
from .questions import load_frozen, write_freeze

ROOT = Path("/home/ubuntu/projects/lecturelens-private/l4")
SEED = 20261118
PATHS = ("rag", "tutor", "study")
RAG_MIN_INTERVAL = 7.0  # Java QA allows 10 requests per user per minute.
JUDGE_URL = "https://api.deepseek.com/chat/completions"
BALANCE_URL = "https://api.deepseek.com/user/balance"
# Balance is read before each repetition and after every 50 judge decisions: often enough to stop
# within about USD 1.5 of judge spend, rare enough to add no measurable load.
BALANCE_EVERY = 50
REFUSAL = (401, 402, 403)
JUDGE_ATTEMPTS = 3
JUDGE_TIMEOUT = 600


def private_write(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("x") as out:
        json.dump(value, out, ensure_ascii=False, indent=1, default=str)
        out.write("\n")
    path.chmod(0o600)


def ledger_for(root):
    plan = json.loads((root / "PLAN.json").read_bytes())
    return Ledger(
        root / "ledger.jsonl",
        hard_stop_usd=plan["budget"]["hard_stop_usd"],
        request_cap_usd=plan["budget"]["per_request_cap_usd"],
    )


def tasks(root):
    return json.loads((root / "ingest/tasks.json").read_text())


def evidence_map(root, lecture):
    data = json.loads((root / "evidence" / f"{lecture}.json").read_text())
    return {e["evidenceId"]: e.get("normalizedText") or e.get("rawText") or "" for e in data["items"]}, data


def cmd_snapshot(args):
    from .runner import Java

    java = Java(args.java, args.root / "ingest/session.local.json")
    for lecture, task in tasks(args.root).items():
        items = java.evidence(task["task_id"])
        revisions = {e["revision"] for e in items}
        if len(revisions) != 1:
            sys.exit(f"{lecture}: mixed revisions {revisions}")
        private_write(
            args.root / "evidence" / f"{lecture}.json",
            {
                "task_id": task["task_id"],
                "revision": revisions.pop(),
                "owner_id": items[0]["ownerId"],
                "items": items,
            },
        )
        print(lecture, len(items))


def schedule(items, rep):
    """Per lecture, a seeded item order; per item, a seeded rotation of the three paths."""
    rng = random.Random(f"{SEED}|rep{rep}")
    order = []
    for lecture in sorted({i["lecture_id"] for i in items}):
        group = [i for i in items if i["lecture_id"] == lecture]
        rng.shuffle(group)
        for item in group:
            start = rng.randrange(3)
            order += [(item, PATHS[(start + k) % 3]) for k in range(3)]
    return order


def cmd_run(args):
    from .runner import Java, run_rag, run_study, run_tutor, tutor_runtime

    items = load_frozen(args.root, args.split)
    if args.items:
        wanted = set(args.items.split(","))
        items = [i for i in items if i["item_id"] in wanted]
    paths = set(args.paths.split(","))
    ledger = ledger_for(args.root)
    java = Java(args.java, args.root / "ingest/session.local.json")
    out = args.root / "runs" / args.split / f"rep{args.rep}"
    phase = f"{args.split}-rep{args.rep}"
    runtime = None
    if "tutor" in paths:
        runtime = tutor_runtime(
            os.environ["AGENT_DATABASE_URL"],
            args.java,
            os.environ["AGENT_SERVICE_SECRET"],
            os.environ["TUTOR_FLASH_API_KEY"],
            ledger,
        )
    last_rag = 0.0
    try:
        for item, path in schedule(items, args.rep):
            if path not in paths:
                continue
            target = out / path / f"{item['item_id']}.json"
            if target.exists():
                continue
            ev = json.loads((args.root / "evidence" / f"{item['lecture_id']}.json").read_text())
            task = ev["task_id"]
            # The product and the judge share one provider account; the count lets the report give a
            # latency subset with no judge request in flight at send time.
            inflight = pipeline.judge_inflight(args.root / "judge" / "inflight.json")
            try:
                if path == "rag":
                    time.sleep(max(0.0, RAG_MIN_INTERVAL - (time.monotonic() - last_rag)))
                    record = run_rag(java, ledger, phase, item, args.rep, task)
                    last_rag = time.monotonic()
                elif path == "study":
                    record = run_study(
                        java, ledger, phase, item, args.rep, task, os.environ["AGENT_DATABASE_URL"]
                    )
                else:
                    scope = {"owner_id": ev["owner_id"], "course_id": task, "revision": ev["revision"]}
                    record = run_tutor(runtime, phase, item, args.rep, scope)
            except BudgetExceeded as error:
                print("STOP budget", error, flush=True)
                return 3
            record["judge_inflight_at_send"] = inflight
            private_write(target, record)
            print(
                phase,
                path,
                item["item_id"],
                record["status"],
                record.get("error_code"),
                record.get("abstained"),
                record.get("latency_ms"),
                flush=True,
            )
    finally:
        if runtime:
            runtime.close()
    print("ledger", json.dumps(ledger.summary()))
    return 0


def study_text(artifact):
    """Learner-visible explanation and reference answers of a Study artifact, in artifact order."""
    parts = []
    for key in ("explanation", "summary", "human_guidance", "reason"):
        if isinstance(artifact.get(key), str):
            parts.append(artifact[key])
    for question in artifact.get("questions") or []:
        for key in ("reference_answer", "answer", "explanation"):
            if isinstance(question.get(key), str):
                parts.append(question[key])
    return "\n\n".join(parts)


def reported_citations(record):
    """Evidence ids the product reports for one ok record (Tutor inline markers are added by normalize)."""
    if record["path"] == "study":
        return [c["evidence_id"] for c in (record["artifact"] or {}).get("citations") or []]
    return list(record["cited"])


def records(root, split, reps):
    """Run records of the given repetitions. Repetition 0 is the smoke run and is scored only on request."""
    for record_path in sorted((root / "runs" / split).glob("rep*/*/*.json")):
        record = json.loads(record_path.read_text())
        if record["rep"] in reps:
            yield record


def responses(root, split, label, reps):
    out = []
    for record in records(root, split, reps):
        if record["status"] != "ok":
            continue
        evidence, _ = evidence_map(root, record["lecture_id"])
        cited = reported_citations(record)
        if record["path"] == "study":
            norm = normalize(study_text(record["artifact"] or {}), cited, evidence)
        else:
            norm = normalize(record["text"], cited, evidence, inline=record["path"] == "tutor")
        out.append(
            {
                "path": record["path"],
                "rep": record["rep"],
                "item_id": record["item_id"],
                "abstained": record["abstained"],
                **norm,
            }
        )
    return out


def cmd_packet(args):
    items = load_frozen(args.root, args.split)
    packet, mapping = blind.build(responses(args.root, args.split, args.label, args.reps), items, seed=SEED)
    base = args.root / "judge" / args.split / args.label
    private_write(base / "packet.json", packet)
    private_write(base / "judge-only-mapping.json", mapping)
    print(len(packet["entries"]), mapping["packet_sha256"])


def judge_one(entry, ledger, phase, key, raw_dir, limit, counter):
    body = judge.request_body(entry)
    reason = "NO_ATTEMPT"
    for attempt in range(1, JUDGE_ATTEMPTS + 1):
        status, payload = None, None
        # The slot is taken before the reservation, so a stopped run never leaves a reservation open.
        with limit:
            reservation = ledger.reserve(
                phase=phase,
                arm="judge",
                unit=f"{entry['response_id']}#{attempt}",
                model=judge.MODEL,
                upper_nano=judge.reservation_nano(body),
            )
            sent = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
            try:
                with counter:
                    response = httpx.post(
                        JUDGE_URL,
                        json=body,
                        timeout=JUDGE_TIMEOUT,
                        headers={"Authorization": "Bearer " + key},
                    )
                status = response.status_code
                payload = response.json()
            except (httpx.HTTPError, ValueError) as error:
                ledger.uncertain(reservation, type(error).__name__ if status is None else f"HTTP_{status}")
                reason = "TRANSPORT" if status is None else f"HTTP_{status}"
            else:
                usage = payload.get("usage") if isinstance(payload, dict) else None
                if usage:
                    ledger.settle(reservation, [{"model": judge.MODEL, "at": sent, "usage": usage}])
                else:
                    ledger.uncertain(reservation, f"HTTP_{status}")
                (raw_dir / f"{entry['response_id']}.{attempt}.json").write_text(
                    json.dumps(payload, ensure_ascii=False)
                )
        limit.record(status)
        if status in REFUSAL:
            # Account-level refusal: stop every thread now; requests already in flight just finish.
            limit.stop(f"PROVIDER_REFUSED_{status}")
            raise pipeline.ProviderErrorsPersist(f"PROVIDER_REFUSED_{status}")
        if payload is None:
            continue
        try:
            choice = payload["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ValueError(f"finish_reason {choice.get('finish_reason')}")
            return {**judge.validate(entry, choice["message"]["content"]), "attempts": attempt}
        except (KeyError, IndexError, TypeError, ValueError) as error:
            reason = f"INVALID: {str(error)[:120]}"
    return {**judge.undetermined(entry, reason), "attempts": JUDGE_ATTEMPTS}


def cmd_judge(args):
    base = args.root / "judge" / args.split / args.label
    packet = json.loads((base / "packet.json").read_text())
    decisions_path = base / "decisions.json"
    decisions = json.loads(decisions_path.read_text()) if decisions_path.exists() else {}
    raw_dir = base / "raw"
    raw_dir.mkdir(mode=0o700, exist_ok=True)
    ledger = ledger_for(args.root)
    key = os.environ["L4_JUDGE_API_KEY"]
    todo = [e for e in packet["entries"] if e["response_id"] not in decisions]
    lock = threading.Lock()
    cap = (
        pipeline.HOLDOUT_JUDGE_CONCURRENCY if args.split == "holdout" else pipeline.FALLBACK_JUDGE_CONCURRENCY
    )
    if not 1 <= args.concurrency <= cap:
        sys.exit(f"--concurrency must be 1..{cap} for {args.split}")
    execution = base / "execution.jsonl"

    def degraded(event):
        with execution.open("a") as out:
            out.write(json.dumps({"event": "concurrency_fallback", **event}) + "\n")
        execution.chmod(0o600)
        print("FALLBACK", json.dumps(event), flush=True)

    limit = pipeline.AdaptiveLimit(
        args.concurrency, min(args.concurrency, pipeline.FALLBACK_JUDGE_CONCURRENCY), degraded
    )
    counter = pipeline.InflightCounter(args.root / "judge" / "inflight.json")

    done_here = [0]

    def work(entry):
        decision = judge_one(entry, ledger, f"judge-{args.split}-{args.label}", key, raw_dir, limit, counter)
        with lock:
            decisions[entry["response_id"]] = decision
            tmp = decisions_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(decisions, ensure_ascii=False))
            tmp.chmod(0o600)
            tmp.replace(decisions_path)
            done_here[0] += 1
            check = args.split == "holdout" and done_here[0] % BALANCE_EVERY == 0
        print(entry["response_id"], decision["verdict"], decision.get("attempts"), flush=True)
        if check:
            state = balance_state(args.root, args.split, key)
            print("BALANCE", json.dumps(state), flush=True)
            if not state["sufficient"]:
                limit.stop("BALANCE_LOW")

    stopped = None
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(work, entry) for entry in todo]
        for future in futures:
            try:
                future.result()
            except pipeline.ProviderErrorsPersist as error:
                stopped = stopped or str(error)
    print("judged", len(decisions), "of", len(packet["entries"]), "fallback", json.dumps(limit.degraded))
    print("ledger", json.dumps(ledger.summary()))
    if stopped or limit.stopped:
        print("STOP", stopped or limit.stopped, flush=True)
        return 5
    return 0


def ok_records(root, split):
    """(path, rep, item) of every status-ok scored record (repetition 0, the smoke run, excluded)."""
    return {
        (r["path"], r["rep"], r["item_id"]) for r in records(root, split, {1, 2, 3}) if r["status"] == "ok"
    }


def revealed(root, split, labels):
    """{(path, rep, item): decision} from one packet, or from verified per-repetition packets."""
    judge_root = root / "judge" / split
    if len(labels) > 1:
        pipeline.verify_sources(judge_root, labels, ok_records(root, split))
    joined = {}
    for label in labels:
        base = judge_root / label
        packet = json.loads((base / "packet.json").read_text())
        mapping = json.loads((base / "judge-only-mapping.json").read_text())
        decisions = json.loads((base / "decisions.json").read_text())
        for r in blind.reveal(packet, mapping, decisions):
            joined[(r["path"], r["rep"], r["item_id"])] = r["decision"]
    return joined


def rows(root, split, labels, reps):
    joined = revealed(root, split, labels)
    items = {i["item_id"]: i for i in load_frozen(root, split)}
    spans = {}
    out = []
    for record in records(root, split, reps):
        item = items[record["item_id"]]
        decision = joined.get((record["path"], record["rep"], record["item_id"]), {})
        hit = None
        if record["status"] == "ok" and item["answerable"]:
            if item["lecture_id"] not in spans:
                _, snapshot = evidence_map(root, item["lecture_id"])
                spans[item["lecture_id"]] = {e["evidenceId"]: e for e in snapshot["items"]}
            ids = reported_citations(record)
            if record["path"] == "tutor":
                ids += re.findall(r"\[([^\[\]\s]+)\]", record.get("text") or "")
            hit = scoring.gold_evidence_hit(item, ids, spans[item["lecture_id"]])
        out.append(
            {
                "path": record["path"],
                "rep": record["rep"],
                "item_id": item["item_id"],
                "lecture_id": item["lecture_id"],
                "language": item["language"],
                "category": item["category"],
                "answerable": item["answerable"],
                "status": record["status"],
                "error_code": record.get("error_code"),
                "abstained": bool(record.get("abstained")),
                "verdict": decision.get("verdict"),
                "vital_lenient": decision.get("vital_lenient", 0.0),
                "vital_supported": decision.get("vital_supported", 0),
                "vital_total": decision.get("vital_total", 0),
                "all_lenient": decision.get("all_lenient", 0.0),
                "material_error": decision.get("material_error"),
                "claims_supported": decision.get("claims_supported", 0),
                "claims_total": decision.get("claims_total", 0),
                "citation_pairs_precise": decision.get("citation_pairs_precise", 0),
                "citation_pairs_total": decision.get("citation_pairs_total", 0),
                "citations_relevant": decision.get("citations_relevant", 0),
                "citations_distinct": decision.get("citations_distinct", 0),
                "gold_evidence_hit": hit,
                "abstention_leak": decision.get("abstention_leak"),
                "cost_nano": record.get("cost_nano"),
                "latency_ms": record.get("latency_ms"),
                "judge_inflight_at_send": record.get("judge_inflight_at_send"),
            }
        )
    return out


def sources(args):
    return args.sources.split(",") if args.sources else [args.label]


def source_reps(args):
    if not args.sources:
        return args.reps
    judge_root = args.root / "judge" / args.split
    return {
        where["rep"]
        for label in sources(args)
        for where in json.loads((judge_root / label / "judge-only-mapping.json").read_text())[
            "responses"
        ].values()
    }


def cmd_verify(args):
    report = pipeline.verify_sources(
        args.root / "judge" / args.split, sources(args), ok_records(args.root, args.split)
    )
    print(json.dumps(report))


def cmd_score(args):
    data = rows(args.root, args.split, sources(args), source_reps(args))
    quiet = [r for r in data if r.get("judge_inflight_at_send") == 0]
    summary = {
        "split": args.split,
        "label": args.label,
        "rows": len(data),
        "metrics": scoring.summarize(data),
        "repetition_range": {m: scoring.repetition_range(data, m) for m in scoring.METRICS},
        "mcnemar_rep1": scoring.mcnemar_pairs(data),
        "latency_cost": scoring.latency_cost(data),
        "latency_cost_no_judge_in_flight": scoring.latency_cost(quiet) if quiet else None,
        "sources": sources(args),
    }
    base = args.root / "judge" / args.split / args.label
    private_write(base / f"rows-{time.strftime('%Y%m%dT%H%M%S')}.json", data)
    private_write(base / f"summary-{time.strftime('%Y%m%dT%H%M%S')}.json", summary)
    for metric, value in summary["metrics"]["metrics"].items():
        print(metric, {p: v["estimate"] for p, v in value["paths"].items()})


def cmd_agreement(args):
    base = args.root / "judge" / args.split / args.label
    labels = sources(args)
    if len(labels) > 1:
        pipeline.verify_sources(args.root / "judge" / args.split, labels, ok_records(args.root, args.split))
    entries, mapping, decisions = pipeline.merged(args.root / "judge" / args.split, labels)
    target = args.root / "runs" / args.split / "agreement"
    if args.by_course:
        lectures = {i["item_id"]: i["lecture_id"] for i in load_frozen(args.root, args.split)}
        packets = pipeline.agreement_by_course(entries, mapping, decisions, lectures, seed=SEED)
        for course, (review, key) in packets.items():
            private_write(target / course / "review-packet.json", review)
            private_write(base / "agreement" / course / "judge-only-key.json", key)
            print(course, len(review["entries"]), key["packet_sha256"])
        total = sum(len(r["entries"]) for r, _ in packets.values())
        print("total", total, "of", len(mapping), f"{total / len(mapping):.1%}")
        return
    packet = {"entries": entries}
    review, key = blind.agreement_sample(packet, {"responses": mapping}, decisions, seed=SEED)
    private_write(target / "review-packet.json", review)
    private_write(base / "agreement" / "judge-only-key.json", key)
    print(len(review["entries"]), key["packet_sha256"])


def cmd_gate(args):
    """Projected spend for the repetition cost gate (PLAN repetitions.cost_gate)."""
    plan = json.loads((args.root / "PLAN.json").read_bytes())
    limit = plan["repetitions"]["cost_gate_usd"]
    ledger = ledger_for(args.root)
    units = ledger.state(ledger.events())
    judge_root = args.root / "judge" / args.split
    labels = sources(args)
    judged = sum(
        len(json.loads((judge_root / lab / "decisions.json").read_text()))
        for lab in labels
        if (judge_root / lab / "decisions.json").exists()
    )
    run_ok = len(ok_records(args.root, args.split))
    judge_costs = [
        u["cost_nano"] for u in units.values() if u["arm"] == "judge" and u["cost_nano"] is not None
    ]
    judge_mean = sum(judge_costs) / len(judge_costs) if judge_costs else 0
    product = sum(
        u["cost_nano"] or u["upper_nano"]
        for u in units.values()
        if u["arm"] != "judge" and u["phase"].startswith(f"{args.split}-rep")
    )
    per_rep = product / args.done
    projected = pipeline.projected_spend(
        committed_nano=ledger.totals(units)["committed_nano"] + ledger.totals(units)["outstanding_nano"],
        pending_judge=max(0, run_ok - judged),
        judge_mean_nano=judge_mean,
        remaining_reps=args.total - args.done,
        product_rep_nano=per_rep,
        entries_per_rep=run_ok / args.done,
    )
    verdict = "OPEN" if projected <= limit * 1e9 else "CLOSED"
    print(
        json.dumps(
            {
                "projected_usd": projected / 1e9,
                "gate_usd": limit,
                "gate": verdict,
                "judged": judged,
                "ok_records": run_ok,
                "judge_mean_usd": judge_mean / 1e9,
                "product_per_rep_usd": per_rep / 1e9,
            }
        )
    )
    return 0 if verdict == "OPEN" else 4


def remaining_estimate(root, split):
    """Estimated USD still to spend in the campaign (pipeline.remaining_spend over ledger observations)."""
    plan = json.loads((root / "PLAN.json").read_bytes())
    units_total = plan["repetitions"][split] * len(load_frozen(root, split)) * len(PATHS)
    runs = list(records(root, split, {1, 2, 3}))
    ok = sum(r["status"] == "ok" for r in runs)
    ledger = ledger_for(root)
    units = list(ledger.state(ledger.events()).values())
    product = [
        u["cost_nano"]
        for u in units
        if u["arm"] in PATHS and u["status"] == "settled" and u["phase"].startswith(f"{split}-rep")
    ]
    judge_costs = [u["cost_nano"] for u in units if u["arm"] == "judge" and u["status"] == "settled"]
    judge_root = root / "judge" / split
    judged = sum(len(json.loads(d.read_text())) for d in judge_root.glob("*/decisions.json"))
    nano = pipeline.remaining_spend(
        units_total=units_total,
        units_done=len(runs),
        product_unit_nano=sum(product) / len(product) if product else 0,
        ok_rate=ok / len(runs) if runs else 1.0,
        judged=judged,
        ok_records=ok,
        judge_mean_nano=sum(judge_costs) / len(judge_costs) if judge_costs else 0,
    )
    return nano / 1e9


def utcnow_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())


def balance_state(root, split, key):
    """Read-only, free provider balance call; the key is sent in a header and never logged."""
    response = httpx.get(BALANCE_URL, headers={"Authorization": "Bearer " + key}, timeout=30)
    response.raise_for_status()
    balance = pipeline.balance_usd(response.json())
    remaining = remaining_estimate(root, split)
    return {
        "at": utcnow_iso(),
        "balance_usd": balance,
        "remaining_usd": remaining,
        "required_usd": pipeline.BALANCE_MARGIN * remaining,
        "sufficient": pipeline.balance_sufficient(balance, remaining),
    }


def append_log(path, event):
    with path.open("a") as out:
        out.write(json.dumps({"at": utcnow_iso(), **event}, ensure_ascii=False) + "\n")
    path.chmod(0o600)


def cmd_balance(args):
    state = balance_state(args.root, args.split, os.environ["L4_JUDGE_API_KEY"])
    append_log(args.root / "runs" / f"{args.split}-balance.jsonl", state)
    print(json.dumps(state))
    return 0 if state["sufficient"] else 6


def cmd_rerun(args):
    """Move failed records aside (once per unit) so `run` repeats them; a missing record is logged only."""
    base = args.root / "runs" / args.split / f"rep{args.rep}"
    log = args.root / "runs" / args.split / "reruns.jsonl"
    for unit in args.units.split(","):
        path, item = unit.split(":")
        target = base / path / f"{item}.json"
        aside = base / "superseded" / path / f"{item}.json"
        if aside.exists():
            sys.exit(f"{unit}: already rerun once")
        if target.exists():
            record = json.loads(target.read_text())
            if record["status"] == "ok":
                sys.exit(f"{unit}: record is ok; only failed units are rerun")
            aside.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            target.replace(aside)
            error = record.get("error_code")
        else:
            private_write(aside, {"missing": True, "reason": args.reason})
            error = "NO_RECORD"
        append_log(
            log,
            {
                "rep": args.rep,
                "path": path,
                "item_id": item,
                "reason": args.reason,
                "superseded_error": error,
            },
        )
        print("rerun", unit, args.reason)


def cmd_rejudge(args):
    """Move decisions aside (once per entry) so `judge` repeats them."""
    base = args.root / "judge" / args.split / args.label
    decisions = json.loads((base / "decisions.json").read_text())
    log = base / "rejudged.jsonl"
    done = (
        {json.loads(line)["response_id"] for line in log.read_text().splitlines()} if log.exists() else set()
    )
    for rid in args.ids.split(","):
        if rid in done:
            sys.exit(f"{rid}: already rejudged once")
        append_log(log, {"response_id": rid, "reason": args.reason, "superseded": decisions.pop(rid)})
        # Keep the raw provider replies of the superseded attempts; the repeat writes the same names.
        aside = base / "raw" / "superseded"
        for raw in sorted((base / "raw").glob(f"{rid}.*.json")):
            aside.mkdir(mode=0o700, parents=True, exist_ok=True)
            raw.replace(aside / raw.name)
        print("rejudge", rid, args.reason)
    tmp = (base / "decisions.json").with_suffix(".tmp")
    tmp.write_text(json.dumps(decisions, ensure_ascii=False))
    tmp.chmod(0o600)
    tmp.replace(base / "decisions.json")


def cmd_freeze(args):
    print(write_freeze(args.root, audit_paths=args.audit, note=args.note))


def cmd_ledger(args):
    print(json.dumps(ledger_for(args.root).summary()))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--java", default="http://127.0.0.1:38080")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("snapshot")
    sub.add_parser("ledger")
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--audit", type=Path, action="append", required=True)
    freeze.add_argument("--note", default="")
    run = sub.add_parser("run")
    run.add_argument("--split", choices=["dev", "holdout"], required=True)
    run.add_argument("--rep", type=int, required=True)
    run.add_argument("--paths", default=",".join(PATHS))
    run.add_argument("--items")
    rerun = sub.add_parser("rerun")
    rerun.add_argument("--split", choices=["dev", "holdout"], required=True)
    rerun.add_argument("--rep", type=int, required=True)
    rerun.add_argument("--units", required=True)
    rerun.add_argument("--reason", required=True)
    rejudge = sub.add_parser("rejudge")
    rejudge.add_argument("--split", choices=["dev", "holdout"], required=True)
    rejudge.add_argument("--label", required=True)
    rejudge.add_argument("--ids", required=True)
    rejudge.add_argument("--reason", required=True)
    for name in ("packet", "judge", "score", "agreement", "verify", "gate", "balance"):
        p = sub.add_parser(name)
        p.add_argument("--split", choices=["dev", "holdout"], required=True)
        p.add_argument("--label", required=name not in ("verify", "gate", "balance"))
        p.add_argument("--reps", type=lambda v: {int(r) for r in v.split(",")}, default={1, 2, 3})
        p.add_argument("--sources", help="comma-separated per-repetition packet labels")
        if name == "judge":
            p.add_argument("--concurrency", type=int, default=pipeline.FALLBACK_JUDGE_CONCURRENCY)
        if name == "agreement":
            p.add_argument("--by-course", action="store_true")
        if name == "gate":
            p.add_argument("--done", type=int, required=True, help="finished repetitions")
            p.add_argument("--total", type=int, default=3)
    args = parser.parse_args(argv)
    return {
        "snapshot": cmd_snapshot,
        "ledger": cmd_ledger,
        "freeze": cmd_freeze,
        "run": cmd_run,
        "packet": cmd_packet,
        "judge": cmd_judge,
        "score": cmd_score,
        "agreement": cmd_agreement,
        "verify": cmd_verify,
        "gate": cmd_gate,
        "balance": cmd_balance,
        "rerun": cmd_rerun,
        "rejudge": cmd_rejudge,
    }[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
